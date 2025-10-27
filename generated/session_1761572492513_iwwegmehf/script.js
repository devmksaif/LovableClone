// DOM Element Selection
const display = document.querySelector('.display-field');
const buttons = document.querySelectorAll('.calculator-buttons button');
const themeToggle = document.querySelector('.theme-toggle');

// Calculator State Variables
let currentInput = '';
let operator = null;
let previousInput = '';
let isNewCalculation = true; // To reset display after an operation or equals

// Event Listeners
buttons.forEach(button => {
    button.addEventListener('click', (e) => {
        const value = e.target.dataset.value;
        // Placeholder for handling button clicks
        // This will be expanded in the next steps
        console.log(`Button clicked: ${value}`);
    });
});

themeToggle.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    // Save theme preference to localStorage (optional, but good for persistence)
    if (document.body.classList.contains('dark-mode')) {
        localStorage.setItem('theme', 'dark');
    } else {
        localStorage.setItem('theme', 'light');
    }
});

// Load theme preference on page load
document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
    }
});

// Placeholder for Calculation Logic
function calculate(num1, operator, num2) {
    // This function will contain the actual calculation logic
    // based on the operator.
    console.log(`Calculating: ${num1} ${operator} ${num2}`);
    return 0; // Placeholder return
}
