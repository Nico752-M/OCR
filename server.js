const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const multer = require('multer');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
    pingTimeout: 60000,
    pingInterval: 25000,
    transports: ['websocket', 'polling']
});

// ✅ PRIMERO: Servir archivos estáticos (IGUAL QUE EL QUE FUNCIONA)
app.use(express.static('public'));

// ✅ SEGUNDO: Redirección (DESPUÉS de static)
app.get('/', (req, res) => {
    res.redirect('/operador.html');
});

// Configuración de multer para subir archivos
const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        const uploadDir = path.join(__dirname, 'uploads');
        if (!fs.existsSync(uploadDir)) {
            fs.mkdirSync(uploadDir, { recursive: true });
        }
        cb(null, uploadDir);
    },
    filename: (req, file, cb) => {
        const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
        cb(null, 'ocr-' + uniqueSuffix + path.extname(file.originalname));
    }
});

const upload = multer({ 
    storage: storage,
    limits: { fileSize: 10 * 1024 * 1024 }
});

// Variable para almacenar los últimos datos OCR
let ultimosDatosOCR = {
    vehiculo: {},
    persona: {},
    licencia: {}
};

// Middleware para logs
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
    next();
});

// Ruta de salud para monitoreo
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        uptime: process.uptime(),
        clients: io.engine.clientsCount
    });
});

// ENDPOINT PARA OCR
app.post('/api/ocr', upload.single('image'), (req, res) => {
    if (!req.file) {
        return res.status(400).json({ error: 'No se subió ninguna imagen' });
    }

    const imagePath = req.file.path;
    const tipo = req.body.tipo || 'propiedad';

    console.log(`Procesando OCR para ${tipo}: ${imagePath}`);

    // Ejecutar script de Python
    const pythonProcess = spawn('python', [path.join(__dirname, 'ocr_processor.py'), imagePath, tipo], {
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' }
    });

    let resultado = '';
    let error = '';

    pythonProcess.stdout.on('data', (data) => {
        resultado += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
        const chunk = data.toString('utf8');
        error += chunk;

        chunk
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean)
            .forEach((line) => {
                if (/traceback|error|exception/i.test(line)) {
                    console.error(`Error Python: ${line}`);
                } else {
                    console.log(`OCR log: ${line}`);
                }
            });
    });

    pythonProcess.on('close', (code) => {
        // Eliminar archivo temporal
        fs.unlink(imagePath, (err) => {
            if (err) console.error('Error eliminando archivo:', err);
        });

        if (code !== 0) {
            return res.status(500).json({ 
                error: 'Error procesando OCR',
                details: error
            });
        }

        try {
            const datos = JSON.parse(resultado);
            
            // Guardar los datos según el tipo
            if (tipo === 'propiedad') {
                ultimosDatosOCR.vehiculo = datos;
            } else if (tipo === 'cedula') {
                ultimosDatosOCR.persona = datos;
            } else if (tipo === 'licencia') {
                ultimosDatosOCR.licencia = datos;
            }
            
            // Emitir a todos los clientes conectados via Socket.io
            io.emit('ocr_completado', {
                tipo: tipo,
                datos: datos
            });
            
            res.json(datos);
        } catch (e) {
            res.json({ texto: resultado });
        }
    });
});

// Endpoint para obtener los últimos datos OCR
app.get('/api/ultimos-datos', (req, res) => {
    res.json(ultimosDatosOCR);
});

// Endpoint para confirmar datos editados desde operador
app.post('/api/confirmar-datos', express.json(), (req, res) => {
    const { vehiculo = {}, persona = {}, licencia = {} } = req.body || {};

    ultimosDatosOCR = {
        vehiculo: { ...ultimosDatosOCR.vehiculo, ...vehiculo },
        persona: { ...ultimosDatosOCR.persona, ...persona },
        licencia: { ...ultimosDatosOCR.licencia, ...licencia }
    };

    io.emit('datos_actualizados', ultimosDatosOCR);

    return res.json({ ok: true, datos: ultimosDatosOCR });
});

// Configurar Socket.io
io.on('connection', (socket) => {
    console.log(`Cliente conectado: ${socket.id}`);
    
    // Enviar los últimos datos al cliente que se conecta
    socket.emit('datos_iniciales', ultimosDatosOCR);
    
    socket.on('disconnect', () => {
        console.log(`Cliente desconectado: ${socket.id}`);
    });
    
    socket.on('error', (error) => {
        console.error(`Error en socket:`, error);
    });
});

// Iniciar servidor
const PORT = process.env.PORT || 3001;
server.listen(PORT, "0.0.0.0", () => {
    console.log(`\n========================================`);
    console.log(`✅ SERVIDOR OCR CORRIENDO`);
    console.log(`========================================`);
    console.log(`📱 Local: http://localhost:${PORT}`);
    
    // Mostrar IPs disponibles
    const { networkInterfaces } = require('os');
    const nets = networkInterfaces();
    for (const name of Object.keys(nets)) {
        for (const net of nets[name]) {
            if (net.family === 'IPv4' && !net.internal) {
                console.log(`📱 Red: http://${net.address}:${PORT}`);
            }
        }
    }
    console.log(`========================================`);
    console.log(`👁️  Vista empleado: http://localhost:${PORT}/operador.html`);
    console.log(`📊 Monitoreo: http://localhost:${PORT}/health`);
    console.log(`========================================\n`);
});

// Manejar cierre limpio
process.on('SIGINT', () => {
    console.log('\nApagando servidor...');
    io.close();
    server.close(() => {
        console.log('Servidor apagado correctamente');
        process.exit(0);
    });
});