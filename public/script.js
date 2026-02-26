async function procesar() {
  try {
    const formData = new FormData();

    const archivos = [
      "cedula_frontal","cedula_reverso",
      "licencia_frontal",
      "tarjeta_frontal"
    ];

    archivos.forEach(id => {
      const file = document.getElementById(id).files[0];
      if (file) formData.append(id, file);
    });

    console.log("📤 Enviando imágenes...");

    const res = await fetch("/ocr", {
      method: "POST",
      body: formData
    });

    if (!res.ok) throw new Error("Error en servidor");

    const data = await res.json();
    console.log("📥 OCR recibido:", data);

    // PERSONA
    document.getElementById("Tipo_documento").value = data.cedula.tipo_documento || "";
    document.getElementById("persona_documento").value = data.cedula.numero || "";
    document.getElementById("persona_nombres").value = data.cedula.nombres || "";
    document.getElementById("persona_apellidos").value = data.cedula.apellidos || "";
    document.getElementById("persona_fecha_nacimiento").value = data.cedula.fecha_nacimiento || "";
    document.getElementById("persona_lugar_nacimiento").value = data.cedula.lugar_nacimiento || "";
    document.getElementById("persona_fecha_expedicion").value = data.cedula.fecha_expedicion || "";
    document.getElementById("persona_lugar_expedicion").value = data.cedula.lugar_expedicion || "";

    // VEHÍCULO
    document.getElementById("vehiculo_identificacion").value = data.tarjeta.identificacion || "";
    document.getElementById("vehiculo_placa").value = data.tarjeta.placa || "";
    document.getElementById("vehiculo_marca").value = data.tarjeta.marca || "";
    document.getElementById("vehiculo_linea").value = data.tarjeta.linea || "";
    document.getElementById("vehiculo_modelo").value = data.tarjeta.modelo || "";
    document.getElementById("vehiculo_cilindraje").value = data.tarjeta.cilindrada|| "";
    document.getElementById("vehiculo_color").value = data.tarjeta.color || "";
    document.getElementById("vehiculo_servicio").value = data.tarjeta.servicio || "";
    document.getElementById("vehiculo_clase").value = data.tarjeta.clase || "";
    document.getElementById("vehiculo_capacidad").value = data.tarjeta.capacidad || "";
    document.getElementById("vehiculo_motor").value = data.tarjeta.motor || "";
    document.getElementById("vehiculo_vin").value = data.tarjeta.vin || "";
    document.getElementById("vehiculo_chasis").value = data.tarjeta.numero || "";
    document.getElementById("vehiculo_serie").value = data.tarjeta.serie || "";

    alert("✅ Documentos procesados correctamente");

  } catch (error) {
    console.error("❌ Error:", error);
    alert("❌ Error procesando documentos. Revisa consola.");
  }
}