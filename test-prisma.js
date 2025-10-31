const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function test() {
  try {
    const sandboxes = await prisma.sandbox.findMany();
    console.log(`Found ${sandboxes.length} sandboxes in database:`);
    sandboxes.forEach(sandbox => {
      console.log(`- ID: ${sandbox.sandboxId}, Type: ${sandbox.type}, Status: ${sandbox.status}, Created: ${sandbox.createdAt}`);
    });
  } catch (error) {
    console.error('Error:', error);
  } finally {
    await prisma.$disconnect();
  }
}

test();