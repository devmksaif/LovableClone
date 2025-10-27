
class Calculator {
    constructor(displayElement) {
        this.displayElement = displayElement;
        this.clear();
    }

    clear() {
        this.currentInput = '';
        this.previousInput = '';
        this.operator = undefined;
        this.updateDisplay();
    }

    appendNumber(number) {
        if (number === '.' && this.currentInput.includes('.')) return;
        this.currentInput = this.currentInput.toString() + number.toString();
        this.updateDisplay();
    }

    chooseOperator(operator) {
        if (this.currentInput === '') return;
        if (this.previousInput !== '') {
            this.compute();
        }
        this.operator = operator;
        this.previousInput = this.currentInput;
        this.currentInput = '';
        this.updateDisplay();
    }

    compute() {
        let computation;
        const prev = parseFloat(this.previousInput);
        const current = parseFloat(this.currentInput);
        if (isNaN(prev) || isNaN(current)) return;
        switch (this.operator) {
            case '+':
                computation = prev + current;
                break;
            case '-':
                computation = prev - current;
                break;
            case '×':
                computation = prev * current;
                break;
            case '÷':
                computation = prev / current;
                break;
            case '%':
                computation = prev % current;
                break;
            default:
                return;
        }
        this.currentInput = computation;
        this.operator = undefined;
        this.previousInput = '';
        this.updateDisplay();
    }

    getDisplayNumber(number) {
        const stringNumber = number.toString();
        const integerDigits = parseFloat(stringNumber.split('.')[0]);
        const decimalDigits = stringNumber.split('.')[1];
        let integerDisplay;
        if (isNaN(integerDigits)) {
            integerDisplay = '';
        } else {
            integerDisplay = integerDigits.toLocaleString('en', { maximumFractionDigits: 0 });
        }
        if (decimalDigits != null) {
            return `${integerDisplay}.${decimalDigits}`;
        } else {
            return integerDisplay;
        }
    }

    updateDisplay() {
        this.displayElement.innerText = this.getDisplayNumber(this.currentInput);
        if (this.operator != null) {
            this.displayElement.innerText = `${this.getDisplayNumber(this.previousInput)} ${this.operator} ${this.getDisplayNumber(this.currentInput)}`;
        } else {
            this.displayElement.innerText = this.getDisplayNumber(this.currentInput);
        }
    }
}

const display = document.querySelector('.display');
const numberButtons = document.querySelectorAll('[data-number]');
const operatorButtons = document.querySelectorAll('[data-operator]');
const equalsButton = document.querySelector('[data-equals]');
const clearButton = document.querySelector('[data-clear]');
const deleteButton = document.querySelector('[data-delete]');
const themeToggleButton = document.querySelector('.theme-toggle');

const calculator = new Calculator(display);

numberButtons.forEach(button => {
    button.addEventListener('click', () => {
        calculator.appendNumber(button.innerText);
    });
});

operatorButtons.forEach(button => {
    button.addEventListener('click', () => {
        calculator.chooseOperator(button.innerText);
    });
});

equalsButton.addEventListener('click', button => {
    calculator.compute();
});

clearButton.addEventListener('click', button => {
    calculator.clear();
});

deleteButton.addEventListener('click', button => {
    calculator.currentInput = calculator.currentInput.toString().slice(0, -1);
    calculator.updateDisplay();
});

// Theme toggle logic
themeToggleButton.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
});
