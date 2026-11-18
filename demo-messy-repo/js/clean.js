function safeParse(text) {
  try {
    return JSON.parse(text);
  } catch (err) {
    console.error("parse failed", err);
    return null;
  }
}

const double = (n) => n * 2;

module.exports = { safeParse, double };
