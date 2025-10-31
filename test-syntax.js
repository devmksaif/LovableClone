// Test file with syntax issues for validation
function testFunction() {
  console.log("This is a test")
  let x = undefined
  if (x = 5) {
    return x
  }
  // Missing closing brace will be added later
}