const fs = require("fs");
const path = require("path");

const source = path.join(__dirname, "..", "contracts");
const destination = path.join(__dirname, "public", "contracts");

if (!fs.existsSync(source)) {
  console.error("Contracts folder not found:", source);
  process.exit(1);
}

fs.rmSync(destination, { recursive: true, force: true });
fs.cpSync(source, destination, { recursive: true });

console.log("Contracts synced successfully!");
console.log("Destination:", destination);
console.log("Files:", fs.readdirSync(destination).length);