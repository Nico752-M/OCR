const express = require("express");
const multer = require("multer");
const fetch = require("node-fetch");
const FormData = require("form-data");

const app = express();
const upload = multer({ dest: "uploads/" });

app.use(express.static("public"));

app.post("/ocr", upload.any(), async (req, res) => {
  const form = new FormData();

  req.files.forEach(file => {
    form.append(file.fieldname, require("fs").createReadStream(file.path));
  });

  const response = await fetch("http://127.0.0.1:8000/ocr", {
    method: "POST",
    body: form
  });

  const data = await response.json();
  res.json(data);
});

app.listen(3001, () => {
  console.log("🟢 Node activo en http://localhost:3001");
});