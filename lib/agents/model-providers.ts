import { ChatGroq } from '@langchain/groq';
import { ChatGoogleGenerativeAI } from '@langchain/google-genai';
import { ChatOpenAI } from '@langchain/openai';

// Model ID to actual model name mapping
export const getModelName = (modelId: string): string => {
  const modelMappings: Record<string, string> = {
    'groq-mixtral-8x7b': 'mixtral-8x7b-32768',
    'groq-llama-3.1-8b-instant': 'llama-3.1-8b-instant',
    'groq-llama-3.3-70b-versatile': 'llama-3.3-70b-versatile',
    'gemini-2.5-flash': 'gemini-2.5-flash',
    'gemini-2.5-pro': 'gemini-2.5-pro',
  };
  return modelMappings[modelId] || modelId;
};

// Initialize the LLM model with provider selection
export function createLLM(model?: string, streaming: boolean = false) {
  // If a specific model is requested, try to use it
  if (model) {
    const groqApiKey = process.env.GROQ_API_KEY;
    const geminiApiKey = process.env.GEMINI_API_KEY;
    const openRouterApiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY;

    if (model.startsWith('groq-') && groqApiKey) {
      const actualModel = getModelName(model);
      console.log('⚡ Using Groq API (Fastest) - Model:', actualModel);
      return new ChatGroq({
        apiKey: groqApiKey,
        model: actualModel,
        temperature: 0.4,
        
        streaming,
      });
    } else if (model.startsWith('gemini-') && geminiApiKey) {
      const actualModel = getModelName(model);
      console.log('🤖 Using Google Gemini API - Model:', actualModel);
      return new ChatGoogleGenerativeAI({
        apiKey: geminiApiKey,
        model: actualModel,
        temperature: 0.4,
       
        streaming,
      });
    } else if (openRouterApiKey) {
      console.log('🔄 Using OpenRouter API - Model:', model);
      const apiBase = process.env.OPENROUTER_API_BASE ?? process.env.OPENAI_API_BASE ?? 'https://openrouter.ai/api/v1';
      return new ChatOpenAI({
        apiKey: openRouterApiKey,
        configuration: {
          baseURL: apiBase,
        },
        model: model,
        temperature: 0.4,
        streaming,
      });
    }
  }

  // Default priority: Groq (fastest) → Gemini (reliable) → OpenRouter (fallback)
  const groqApiKey = process.env.GROQ_API_KEY;
  const geminiApiKey = process.env.GEMINI_API_KEY;
  const openRouterApiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY;

  if (groqApiKey) {
    console.log('⚡ Using Groq API (Fastest)');
    return new ChatGroq({
      apiKey: groqApiKey,
      model: process.env.GROQ_MODEL ?? 'llama-3.1-8b-instant',
      temperature: 0.7,
      maxTokens: 4096,
      streaming,
    });
  } else if (geminiApiKey) {
    console.log('🤖 Using Google Gemini API');
    return new ChatGoogleGenerativeAI({
      apiKey: geminiApiKey,
      model: process.env.GEMINI_MODEL ?? 'gemini-2.5-flash',
      temperature: 0.7,
      maxOutputTokens: 4096,
      streaming,
    });
  } else if (openRouterApiKey) {
    console.log('🔄 Using OpenRouter API');
    const apiBase = process.env.OPENROUTER_API_BASE ?? process.env.OPENAI_API_BASE ?? 'https://openrouter.ai/api/v1';
    return new ChatOpenAI({
      apiKey: openRouterApiKey,
      configuration: {
        baseURL: apiBase,
      },
      model: process.env.OPENAI_MODEL ?? process.env.OPENROUTER_MODEL ?? 'openai/gpt-4o',
      temperature: 0.7,
      streaming,
    });
  } else {
    throw new Error('No API key found. Set GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY/OPENAI_API_KEY');
  }
}

export let llm = createLLM();