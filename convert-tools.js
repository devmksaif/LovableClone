const fs = require('fs');
const path = require('path');

// Read the tools.ts file
const toolsPath = path.join(__dirname, 'lib', 'agents', 'tools.ts');
let content = fs.readFileSync(toolsPath, 'utf8');

// Function to convert Zod schema to JSON schema
function zodToJsonSchema(zodSchema) {
  // This is a simple converter - for complex schemas you might need more logic
  const lines = zodSchema.split('\n').map(line => line.trim());

  const properties = {};
  const required = [];

  for (const line of lines) {
    if (line.includes('z.string()')) {
      const match = line.match(/(\w+):\s*z\.string\(\)\.describe\('([^']+)'\)/);
      if (match) {
        properties[match[1]] = { type: 'string', description: match[2] };
        required.push(match[1]);
      }
    } else if (line.includes('z.number()')) {
      const match = line.match(/(\w+):\s*z\.number\(\)\.describe\('([^']+)'\)/);
      if (match) {
        properties[match[1]] = { type: 'number', description: match[2] };
        required.push(match[1]);
      }
    } else if (line.includes('z.boolean()')) {
      const match = line.match(/(\w+):\s*z\.boolean\(\)\.describe\('([^']+)'\)/);
      if (match) {
        properties[match[1]] = { type: 'boolean', description: match[2] };
        required.push(match[1]);
      }
    }
  }

  return { properties, required };
}

// Find all tool definitions that still use the old format
const toolRegex = /export const (\w+) = tool\(async \(([^)]+)\) => \{([\s\S]*?)\}, \{\s*name: '([^']+)',\s*description: '([^']+)',\s*schema: z\.object\(\{([\s\S]*?)\}\),\s*\}\);/g;

let match;
while ((match = toolRegex.exec(content)) !== null) {
  const [fullMatch, toolName, params, handlerCode, name, description, schemaStr] = match;

  // Convert schema
  const { properties, required } = zodToJsonSchema(schemaStr);

  // Create new format
  const newTool = `export const ${toolName}: Tool = {
  name: '${name}',
  description: '${description}',
  inputSchema: {
    type: 'object',
    properties: ${JSON.stringify(properties, null, 4)},
    required: ${JSON.stringify(required)}
  },
  handler: async (${params}) => {${handlerCode}
};`;

  // Replace in content
  content = content.replace(fullMatch, newTool);
}

// Write back
fs.writeFileSync(toolsPath, content);
console.log('Conversion completed!');