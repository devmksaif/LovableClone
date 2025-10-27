document.addEventListener('DOMContentLoaded', () => {
    // Select DOM elements
    const display = document.querySelector('.display');
    const buttons = document.querySelectorAll('.button');
    const toggleThemeButton = document.getElementById('toggle-theme');

    // Initialize calculator state
    let currentInput = '0';
    let operator = null;
    let previousInput = null;
    let result = null;
    let waitingForSecondOperand = false;

    // Function to update the display
    function updateDisplay() {
        display.textContent = currentInput;
    }

    // Event listeners will be added here later
});
