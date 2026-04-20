const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const publicDir = path.join(root, "public");

fs.mkdirSync(publicDir, { recursive: true });

const url = (process.env.BRIDGE_PUBLIC_URL || "").trim().replace(/\/$/, "");
const bridgeConfig = `/* Generado en build (Vercel: variable BRIDGE_PUBLIC_URL) */\nwindow.__BRIDGE_BASE__=${JSON.stringify(url)};\n`;
fs.writeFileSync(path.join(root, "bridge-config.js"), bridgeConfig, "utf8");
fs.writeFileSync(path.join(publicDir, "bridge-config.js"), bridgeConfig, "utf8");

for (const file of ["index.html", "app.js"]) {
  fs.copyFileSync(path.join(root, file), path.join(publicDir, file));
}

console.log("Build static OK -> public/");
console.log("BRIDGE_PUBLIC_URL ->", url || "(vacío: usa ?bridge= o localhost)");
