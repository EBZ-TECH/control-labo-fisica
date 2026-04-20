const fs = require("fs");
const path = require("path");

const url = (process.env.BRIDGE_PUBLIC_URL || "").trim().replace(/\/$/, "");
const out = path.join(__dirname, "..", "bridge-config.js");
fs.writeFileSync(
  out,
  `/* Generado en build (Vercel: variable BRIDGE_PUBLIC_URL) */\nwindow.__BRIDGE_BASE__=${JSON.stringify(url)};\n`,
  "utf8"
);
console.log("bridge-config.js ->", url || "(vacío: sólo útil en localhost o ?bridge=)");
