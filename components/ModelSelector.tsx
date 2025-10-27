'use client';

import { useState, useEffect } from 'react';

export interface ModelOption {
  id: string;
  name: string;
  provider: string;
  description: string;
  speed: 'fast' | 'medium' | 'slow';
  cost: 'free' | 'low' | 'medium';
  available: boolean;
}

const AVAILABLE_MODELS: ModelOption[] = [
  {
    id: 'groq-mixtral-8x7b',
    name: 'Mixtral 8x7B (Groq)',
    provider: 'groq',
    description: 'High quality mixture of experts',
    speed: 'medium',
    cost: 'low',
    available: true,
  },
  {
    id: 'groq-llama-3.1-8b-instant',
    name: 'Llama 3.1 8B Instant (Groq)',
    provider: 'groq',
    description: 'Optimized for speed and low latency',
    speed: 'fast',
    cost: 'low',
    available: true,
  },
  {
    id: 'groq-llama-3.3-70b-versatile',
    name: 'Llama 3.3 70B Versatile (Groq)',
    provider: 'groq',
    description: 'Most capable Llama model for complex tasks',
    speed: 'slow',
    cost: 'medium',
    available: true,
  },
  {
    id: 'gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    provider: 'gemini',
    description: 'Google\'s fastest Gemini model',
    speed: 'fast',
    cost: 'free',
    available: true,
  },
  {
    id: 'gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    provider: 'gemini',
    description: 'Google\'s most capable Gemini model',
    speed: 'medium',
    cost: 'free',
    available: true,
  },
  {
    id: 'openrouter-gpt4',
    name: 'GPT-4 (OpenRouter)',
    provider: 'openrouter',
    description: 'OpenAI GPT-4 via OpenRouter',
    speed: 'slow',
    cost: 'medium',
    available: true,
  },
];

interface ModelSelectorProps {
  selectedModel: string;
  onModelChange: (modelId: string) => void;
  className?: string;
}

export default function ModelSelector({ selectedModel, onModelChange, className = '' }: ModelSelectorProps) {
  const [availableModels, setAvailableModels] = useState<ModelOption[]>(AVAILABLE_MODELS);

  // Check which models are actually available based on API keys
  useEffect(() => {
    const checkAvailability = async () => {
      try {
        const response = await fetch('/api/models/available');
        if (response.ok) {
          const availableProviders = await response.json();
          setAvailableModels(models =>
            models.map(model => ({
              ...model,
              available: availableProviders.includes(model.provider)
            }))
          );
        }
      } catch (error) {
        console.warn('Could not check model availability:', error);
      }
    };

    checkAvailability();
  }, []);

  const getSpeedColor = (speed: string) => {
    switch (speed) {
      case 'fast': return 'text-green-600 bg-green-100';
      case 'medium': return 'text-yellow-600 bg-yellow-100';
      case 'slow': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const getCostColor = (cost: string) => {
    switch (cost) {
      case 'free': return 'text-green-600 bg-green-100';
      case 'low': return 'text-blue-600 bg-blue-100';
      case 'medium': return 'text-orange-600 bg-orange-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  return (
    <div className={`space-y-2 ${className}`}>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        AI Model
      </label>
      <select
        value={selectedModel}
        onChange={(e) => onModelChange(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:border-gray-600 dark:text-white"
      >
        {availableModels.map((model) => (
          <option
            key={model.id}
            value={model.id}
            disabled={!model.available}
            className={!model.available ? 'text-gray-400' : ''}
          >
            {model.name} {!model.available && '(Not Available)'}
          </option>
        ))}
      </select>

      {/* Model Info */}
      {selectedModel && (
        <div className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
          {(() => {
            const model = availableModels.find(m => m.id === selectedModel);
            if (!model) return null;

            return (
              <>
                <p>{model.description}</p>
                <div className="flex gap-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getSpeedColor(model.speed)}`}>
                    {model.speed.toUpperCase()} Speed
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getCostColor(model.cost)}`}>
                    {model.cost.toUpperCase()} Cost
                  </span>
                </div>
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}