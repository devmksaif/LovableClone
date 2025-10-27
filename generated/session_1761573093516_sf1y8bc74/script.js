document.addEventListener('DOMContentLoaded', () => {
    const display = document.getElementById('display');
    const buttons = document.querySelectorAll('.buttons button');

    let currentInput = '';
    let operator = null;
    let previousInput = '';

    buttons.forEach(button => {
        button.addEventListener('click', () => {
            const value = button.dataset.value;

            if (button.classList.contains('number')) {
                currentInput += value;
                display.textContent = currentInput;
            } else if (button.classList.contains('operator')) {
                if (currentInput === '') return;
                if (previousInput !== '') {
                    calculate();
                }
                operator = value;
                previousInput = currentInput;
                currentInput = '';
            } else if (button.classList.contains('equals')) {
                calculate();
            } else if (button.classList.contains('clear')) {
                currentInput = '';
                operator = null;
                previousInput = '';
                display.textContent = '0';
            } else if (button.classList.contains('decimal')) {
                if (!currentInput.includes('.')) {
                    currentInput += '.';
                    display.textContent = currentInput;
                }
            } else if (button.classList.contains('percent')) {
                if (currentInput !== '') {
                    currentInput = (parseFloat(currentInput) / 100).toString();
                    display.textContent = currentInput;
                }
            }
        });
    });

    const calculate = () => {
        let result;
        const prev = parseFloat(previousInput);
        const current = parseFloat(currentInput);

        if (isNaN(prev) || isNaN(current)) return;

        switch (operator) {
            case '+':
                result = prev + current;
                break;
            case '-':
                result = prev - current;
                break;
            case '×':
                result = prev * current;
                break;
            case '÷':
                result = prev / current;
                break;
            default:
                return;
        }
        currentInput = result.toString();
        operator = null;
        previousInput = '';
        display.textContent = currentInput;
    };
});
