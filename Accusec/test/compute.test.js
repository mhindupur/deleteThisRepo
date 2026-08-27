/**
 * Lightweight node checks for AccuSec calculator arithmetic helpers.
 * Mirrors the core compute rules used by Accusec/js/calculator.js.
 */

function compute(left, right, operator) {
  switch (operator) {
    case "+":
      return left + right;
    case "−":
      return left - right;
    case "×":
      return left * right;
    case "÷":
      return right === 0 ? NaN : left / right;
    default:
      return right;
  }
}

function assertEqual(actual, expected, label) {
  const pass = Object.is(actual, expected) || (Number.isNaN(actual) && Number.isNaN(expected));
  if (!pass) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
  console.log(`ok - ${label}`);
}

assertEqual(compute(12, 3, "+"), 15, "addition");
assertEqual(compute(12, 3, "−"), 9, "subtraction");
assertEqual(compute(12, 3, "×"), 36, "multiplication");
assertEqual(compute(12, 3, "÷"), 4, "division");
assertEqual(Number.isNaN(compute(12, 0, "÷")), true, "division by zero yields NaN");

console.log("All AccuSec calculator checks passed.");
