"use client";

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Eye, EyeOff, Save, RotateCcw, Key, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ApiKeyConfig {
  groq: string;
  openai: string;
  gemini: string;
  openrouter: string;
}

interface ApiKeySettingsProps {
  onApiKeysChange: (apiKeys: ApiKeyConfig) => void;
  className?: string;
}

export default function ApiKeySettings({ onApiKeysChange, className }: ApiKeySettingsProps) {
  const [apiKeys, setApiKeys] = useState<ApiKeyConfig>({
    groq: '',
    openai: '',
    gemini: '',
    openrouter: ''
  });

  const [showKeys, setShowKeys] = useState<Record<keyof ApiKeyConfig, boolean>>({
    groq: false,
    openai: false,
    gemini: false,
    openrouter: false
  });

  const [hasChanges, setHasChanges] = useState(false);
  const [savedKeys, setSavedKeys] = useState<ApiKeyConfig>({
    groq: '',
    openai: '',
    gemini: '',
    openrouter: ''
  });

  // Load saved API keys from localStorage on component mount
  useEffect(() => {
    const saved = localStorage.getItem('ai-chat-api-keys');
    if (saved) {
      try {
        const parsedKeys = JSON.parse(saved);
        setApiKeys(parsedKeys);
        setSavedKeys(parsedKeys);
        onApiKeysChange(parsedKeys);
      } catch (error) {
        console.error('Failed to parse saved API keys:', error);
      }
    }
  }, [onApiKeysChange]);

  // Check for changes
  useEffect(() => {
    const changed = Object.keys(apiKeys).some(
      key => apiKeys[key as keyof ApiKeyConfig] !== savedKeys[key as keyof ApiKeyConfig]
    );
    setHasChanges(changed);
  }, [apiKeys, savedKeys]);

  const handleKeyChange = (provider: keyof ApiKeyConfig, value: string) => {
    setApiKeys(prev => ({
      ...prev,
      [provider]: value
    }));
  };

  const toggleShowKey = (provider: keyof ApiKeyConfig) => {
    setShowKeys(prev => ({
      ...prev,
      [provider]: !prev[provider]
    }));
  };

  const saveApiKeys = () => {
    try {
      localStorage.setItem('ai-chat-api-keys', JSON.stringify(apiKeys));
      setSavedKeys(apiKeys);
      onApiKeysChange(apiKeys);
      setHasChanges(false);
    } catch (error) {
      console.error('Failed to save API keys:', error);
    }
  };

  const resetChanges = () => {
    setApiKeys(savedKeys);
    setHasChanges(false);
  };

  const clearAllKeys = () => {
    const emptyKeys = {
      groq: '',
      openai: '',
      gemini: '',
      openrouter: ''
    };
    setApiKeys(emptyKeys);
  };

  const getKeyStatus = (key: string) => {
    if (!key) return 'empty';
    if (key.length < 10) return 'invalid';
    return 'valid';
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'valid':
        return <Check className="h-4 w-4 text-green-500" />;
      case 'invalid':
        return <X className="h-4 w-4 text-red-500" />;
      default:
        return <Key className="h-4 w-4 text-gray-400" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'valid':
        return <Badge variant="default" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Valid</Badge>;
      case 'invalid':
        return <Badge variant="destructive">Invalid</Badge>;
      default:
        return <Badge variant="secondary">Empty</Badge>;
    }
  };

  const providers = [
    { key: 'groq' as const, name: 'Groq', description: 'Fast inference for open-source models' },
    { key: 'openai' as const, name: 'OpenAI', description: 'GPT models and advanced AI capabilities' },
    { key: 'gemini' as const, name: 'Google Gemini', description: 'Google\'s multimodal AI models' },
    { key: 'openrouter' as const, name: 'OpenRouter', description: 'Access to multiple AI models' }
  ];

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Key className="h-5 w-5" />
          API Key Settings
        </CardTitle>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Configure your API keys for different AI providers. Keys are stored locally in your browser.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {providers.map((provider) => {
          const keyValue = apiKeys[provider.key];
          const status = getKeyStatus(keyValue);
          const isVisible = showKeys[provider.key];

          return (
            <div key={provider.key} className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium">{provider.name}</label>
                  <p className="text-xs text-gray-500 dark:text-gray-400">{provider.description}</p>
                </div>
                {getStatusBadge(status)}
              </div>
              
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type={isVisible ? "text" : "password"}
                    value={keyValue}
                    onChange={(e) => handleKeyChange(provider.key, e.target.value)}
                    placeholder={`Enter your ${provider.name} API key`}
                    className="pr-20"
                  />
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                    {getStatusIcon(status)}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleShowKey(provider.key)}
                      className="h-6 w-6 p-0"
                    >
                      {isVisible ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        <div className="flex items-center justify-between pt-4 border-t">
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={clearAllKeys}
              disabled={Object.values(apiKeys).every(key => !key)}
            >
              Clear All
            </Button>
            {hasChanges && (
              <Button
                variant="outline"
                size="sm"
                onClick={resetChanges}
              >
                <RotateCcw className="h-4 w-4 mr-1" />
                Reset
              </Button>
            )}
          </div>
          
          <Button
            onClick={saveApiKeys}
            disabled={!hasChanges}
            className="flex items-center gap-2"
          >
            <Save className="h-4 w-4" />
            Save Keys
          </Button>
        </div>

        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
          <p>• API keys are stored locally in your browser and never sent to our servers</p>
          <p>• Keys will be included in requests to the respective AI providers</p>
          <p>• If no key is provided, the system will use fallback keys when available</p>
        </div>
      </CardContent>
    </Card>
  );
}