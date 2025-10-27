import { NextResponse } from 'next/server';

export async function GET() {
  const availableProviders: string[] = [];

  // Check which API keys are configured
  if (process.env.GROQ_API_KEY) {
    availableProviders.push('groq');
  }

  if (process.env.GEMINI_API_KEY) {
    availableProviders.push('gemini');
  }

  if (process.env.OPENROUTER_API_KEY || process.env.OPENAI_API_KEY) {
    availableProviders.push('openrouter');
  }

  return NextResponse.json(availableProviders);
}