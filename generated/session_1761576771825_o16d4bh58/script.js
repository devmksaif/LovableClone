let displayValue = '0';
let firstOperand = null;
let operator = null;
let waitingForSecondOperand = false;

function updateDisplay() {
    const display = document.getElementById('display');
    display.textContent = displayValue;
}

function clearDisplay() {
    displayValue = '0';
    firstOperand = null;
    operator = null;
    waitingForSecondOperand = false;
    updateDisplay();
}

function inputDigit(digit) {
    if (waitingForSecondOperand === true) {
        displayValue = digit;
        waitingForSecondOperand = false;
    } else {
        displayValue = displayValue === '0' ? digit : displayValue + digit;
    }
    updateDisplay();
}

function inputDecimal(dot) {
    if (waitingForSecondOperand === true) return;
    if (!displayValue.includes(dot)) {
        displayValue += dot;
    }
    updateDisplay();
}

function handleOperator(nextOperator) {
    const inputValue = parseFloat(displayValue);

    if (operator && waitingForSecondOperand) {
        operator = nextOperator;
        return;
    }

    if (firstOperand === null) {
        firstOperand = inputValue;
    } else if (operator) {
        const result = operate(firstOperand, inputValue, operator);
        displayValue = String(result);
        firstOperand = result;
    }

    waitingForSecondOperand = true;
    operator = nextOperator;
    updateDisplay();
}

function operate(num1, num2, op) {
    if (op === '+') {
        return num1 + num2;
    } else if (op === '-') {
        return num1 - num2;
    } else if (op === '*') {
        return num1 * num2;
    } else if (op === '/') {
        return num1 / num2;
    }
    return num2;
}

function backspace() {
    displayValue = displayValue.slice(0, -1);
    if (displayValue === '') {
        displayValue = '0';
    }
    updateDisplay();
}

document.addEventListener('DOMContentLoaded', () => {
    updateDisplay();
    const buttons = document.querySelector('.calculator-buttons');
    buttons.addEventListener('click', (event) => {
        const { target } = event;
        if (!target.matches('button')) {
            return;
        }

        if (target.classList.contains('operator')) {
            handleOperator(target.value);
            return;
        }

        if (target.classList.contains('decimal')) {
            inputDecimal(target.value);
            return;
        }

        if (target.classList.contains('clear')) {
            clearDisplay();
            return;
        }

        if (target.classList.contains('backspace')) {
            backspace();
            return;
        }

        inputDigit(target.value);
    });
});
