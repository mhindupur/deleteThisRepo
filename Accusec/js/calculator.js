(() => {
  const displayEl = document.getElementById("display");
  const expressionEl = document.getElementById("expression");
  const keypad = document.getElementById("keypad");

  const state = {
    displayValue: "0",
    firstOperand: null,
    operator: null,
    waitingForSecond: false,
    expression: "",
  };

  const formatNumber = (value) => {
    if (!Number.isFinite(value)) return "Error";
    const text = String(value);
    if (text.includes("e")) return text;
    const [whole, fraction = ""] = text.split(".");
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return fraction ? `${grouped}.${fraction}` : grouped;
  };

  const parseDisplay = () => Number(state.displayValue.replace(/,/g, ""));

  const pulseDisplay = () => {
    displayEl.classList.remove("pulse");
    void displayEl.offsetWidth;
    displayEl.classList.add("pulse");
  };

  const render = () => {
    displayEl.textContent = state.displayValue;
    expressionEl.textContent = state.expression;
  };

  const clearAll = () => {
    state.displayValue = "0";
    state.firstOperand = null;
    state.operator = null;
    state.waitingForSecond = false;
    state.expression = "";
    render();
  };

  const inputDigit = (digit) => {
    if (state.waitingForSecond) {
      state.displayValue = digit;
      state.waitingForSecond = false;
    } else if (state.displayValue === "0") {
      state.displayValue = digit;
    } else if (state.displayValue.replace(/[.,]/g, "").length < 12) {
      state.displayValue += digit;
    }
    render();
  };

  const inputDecimal = () => {
    if (state.waitingForSecond) {
      state.displayValue = "0.";
      state.waitingForSecond = false;
      render();
      return;
    }
    if (!state.displayValue.includes(".")) {
      state.displayValue += ".";
      render();
    }
  };

  const toggleSign = () => {
    if (state.displayValue === "0" || state.displayValue === "Error") return;
    state.displayValue = state.displayValue.startsWith("-")
      ? state.displayValue.slice(1)
      : `-${state.displayValue}`;
    render();
  };

  const toPercent = () => {
    const value = parseDisplay() / 100;
    state.displayValue = formatNumber(value);
    pulseDisplay();
    render();
  };

  const compute = (left, right, operator) => {
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
  };

  const setOperator = (nextOperator) => {
    const inputValue = parseDisplay();

    if (state.operator && state.waitingForSecond) {
      state.operator = nextOperator;
      state.expression = `${formatNumber(state.firstOperand)} ${state.operator}`;
      render();
      return;
    }

    if (state.firstOperand === null) {
      state.firstOperand = inputValue;
    } else if (state.operator) {
      const result = compute(state.firstOperand, inputValue, state.operator);
      state.displayValue = formatNumber(result);
      state.firstOperand = Number.isFinite(result) ? result : null;
      pulseDisplay();
    }

    state.waitingForSecond = true;
    state.operator = nextOperator;
    state.expression = Number.isFinite(state.firstOperand)
      ? `${formatNumber(state.firstOperand)} ${state.operator}`
      : "";
    render();
  };

  const equals = () => {
    if (state.operator === null || state.waitingForSecond) return;
    const inputValue = parseDisplay();
    const result = compute(state.firstOperand, inputValue, state.operator);
    state.expression = `${formatNumber(state.firstOperand)} ${state.operator} ${formatNumber(inputValue)} =`;
    state.displayValue = formatNumber(result);
    state.firstOperand = null;
    state.operator = null;
    state.waitingForSecond = true;
    pulseDisplay();
    render();
  };

  const pressVisual = (button) => {
    button.classList.add("pressed");
    window.setTimeout(() => button.classList.remove("pressed"), 120);
  };

  keypad.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    pressVisual(button);

    if (button.dataset.digit !== undefined) {
      inputDigit(button.dataset.digit);
      return;
    }
    if (button.dataset.op) {
      setOperator(button.dataset.op);
      return;
    }

    switch (button.dataset.action) {
      case "clear":
        clearAll();
        break;
      case "sign":
        toggleSign();
        break;
      case "percent":
        toPercent();
        break;
      case "decimal":
        inputDecimal();
        break;
      case "equals":
        equals();
        break;
      default:
        break;
    }
  });

  const keyMap = {
    Escape: "clear",
    Enter: "equals",
    "=": "equals",
    "%": "percent",
    ".": "decimal",
    "+": "+",
    "-": "−",
    "*": "×",
    "/": "÷",
  };

  window.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;

    if (/^\d$/.test(event.key)) {
      event.preventDefault();
      const button = keypad.querySelector(`[data-digit="${event.key}"]`);
      if (button) pressVisual(button);
      inputDigit(event.key);
      return;
    }

    const mapped = keyMap[event.key];
    if (!mapped) return;
    event.preventDefault();

    if (mapped === "clear") {
      const button = keypad.querySelector('[data-action="clear"]');
      if (button) pressVisual(button);
      clearAll();
      return;
    }
    if (mapped === "equals") {
      const button = keypad.querySelector('[data-action="equals"]');
      if (button) pressVisual(button);
      equals();
      return;
    }
    if (mapped === "percent") {
      const button = keypad.querySelector('[data-action="percent"]');
      if (button) pressVisual(button);
      toPercent();
      return;
    }
    if (mapped === "decimal") {
      const button = keypad.querySelector('[data-action="decimal"]');
      if (button) pressVisual(button);
      inputDecimal();
      return;
    }

    const button = keypad.querySelector(`[data-op="${mapped}"]`);
    if (button) pressVisual(button);
    setOperator(mapped);
  });

  render();
})();
