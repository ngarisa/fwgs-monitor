import React, { useState, useEffect } from 'react';
import { Settings, Save, Play, Square, RefreshCw } from 'lucide-react';
import { MonitorConfig as MonitorConfigType, MonitorStatus } from '../types';
import { storage } from '../utils/storage';
import { api } from '../utils/api';

export const MonitorConfig: React.FC = () => {
  const [config, setConfig] = useState<MonitorConfigType>({
    categoryIds: ['4036262580'],
    scrapeIntervalMinutes: 10,
    discordWebhookUrl: '',
    enableWatchlist: false,
    watchlistIds: [],
    enableAutoCheckout: false,
    autoCheckoutKeywords: [],
    autoCheckoutEvents: ['available', 'new'],
    dryRun: true
  });
  
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [isSaved, setIsSaved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [newKeyword, setNewKeyword] = useState('');
  const [newWatchlistId, setNewWatchlistId] = useState('');

  useEffect(() => {
    const saved = storage.getMonitorConfig();
    if (saved) {
      setConfig(saved);
    }
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const statusData = await api.getMonitorStatus();
      setStatus(statusData);
    } catch (error) {
      console.error('Failed to load status:', error);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    storage.setMonitorConfig(config);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const handleStartMonitor = async () => {
    setIsLoading(true);
    try {
      await api.startMonitor(config);
      await loadStatus();
    } catch (error) {
      console.error('Failed to start monitor:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopMonitor = async () => {
    setIsLoading(true);
    try {
      await api.stopMonitor();
      await loadStatus();
    } catch (error) {
      console.error('Failed to stop monitor:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const addKeyword = () => {
    if (newKeyword.trim() && !config.autoCheckoutKeywords.includes(newKeyword.trim())) {
      setConfig(prev => ({
        ...prev,
        autoCheckoutKeywords: [...prev.autoCheckoutKeywords, newKeyword.trim()]
      }));
      setNewKeyword('');
    }
  };

  const removeKeyword = (keyword: string) => {
    setConfig(prev => ({
      ...prev,
      autoCheckoutKeywords: prev.autoCheckoutKeywords.filter(k => k !== keyword)
    }));
  };

  const addWatchlistId = () => {
    if (newWatchlistId.trim() && !config.watchlistIds.includes(newWatchlistId.trim())) {
      setConfig(prev => ({
        ...prev,
        watchlistIds: [...prev.watchlistIds, newWatchlistId.trim()]
      }));
      setNewWatchlistId('');
    }
  };

  const removeWatchlistId = (id: string) => {
    setConfig(prev => ({
      ...prev,
      watchlistIds: prev.watchlistIds.filter(wid => wid !== id)
    }));
  };

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <div className="card">
        <div className="card-header">
          <Settings className="w-6 h-6 text-primary-600" />
          <div className="flex-1">
            <h2 className="text-xl font-semibold text-gray-900">Monitor Status</h2>
            <p className="text-sm text-gray-600">Current monitoring status and controls</p>
          </div>
          <button
            onClick={loadStatus}
            className="btn btn-secondary"
            disabled={isLoading}
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {status && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-gray-900">{status.totalProducts}</div>
                <div className="text-sm text-gray-600">Total Products</div>
              </div>
              <div className="bg-success-50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-success-700">{status.availableProducts}</div>
                <div className="text-sm text-success-600">Available Now</div>
              </div>
              <div className="bg-primary-50 p-4 rounded-lg">
                <div className={`status-indicator ${status.isRunning ? 'status-running' : 'status-stopped'}`}>
                  <div className={`w-2 h-2 rounded-full ${status.isRunning ? 'bg-success-500 animate-pulse' : 'bg-gray-400'}`} />
                  {status.isRunning ? 'Running' : 'Stopped'}
                </div>
                <div className="text-sm text-gray-600 mt-1">
                  Last update: {new Date(status.lastUpdate).toLocaleTimeString()}
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              {status.isRunning ? (
                <button
                  onClick={handleStopMonitor}
                  className="btn btn-error"
                  disabled={isLoading}
                >
                  <Square className="w-4 h-4" />
                  Stop Monitor
                </button>
              ) : (
                <button
                  onClick={handleStartMonitor}
                  className="btn btn-success"
                  disabled={isLoading}
                >
                  <Play className="w-4 h-4" />
                  Start Monitor
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Configuration Form */}
      <div className="card">
        <div className="card-header">
          <Settings className="w-6 h-6 text-primary-600" />
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Monitor Configuration</h2>
            <p className="text-sm text-gray-600">Configure monitoring settings and automation</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Settings */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-900">Basic Settings</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">Category IDs (comma-separated)</label>
                <input
                  type="text"
                  className="input-field font-mono"
                  value={config.categoryIds.join(', ')}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    categoryIds: e.target.value.split(',').map(id => id.trim()).filter(Boolean)
                  }))}
                  placeholder="4036262580, 3030473779"
                />
              </div>
              
              <div className="input-group">
                <label className="input-label">Scrape Interval (minutes)</label>
                <input
                  type="number"
                  className="input-field"
                  value={config.scrapeIntervalMinutes}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    scrapeIntervalMinutes: parseInt(e.target.value) || 10
                  }))}
                  min="1"
                  max="60"
                />
              </div>
            </div>

            <div className="input-group">
              <label className="input-label">Discord Webhook URL</label>
              <input
                type="url"
                className="input-field"
                value={config.discordWebhookUrl}
                onChange={(e) => setConfig(prev => ({
                  ...prev,
                  discordWebhookUrl: e.target.value
                }))}
                placeholder="https://discord.com/api/webhooks/..."
              />
            </div>
          </div>

          {/* Auto Checkout Settings */}
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-medium text-gray-900">Auto Checkout</h3>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={config.enableAutoCheckout}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    enableAutoCheckout: e.target.checked
                  }))}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-600">Enable</span>
              </label>
            </div>

            {config.enableAutoCheckout && (
              <div className="space-y-4 pl-4 border-l-2 border-primary-200">
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={config.dryRun}
                      onChange={(e) => setConfig(prev => ({
                        ...prev,
                        dryRun: e.target.checked
                      }))}
                      className="rounded border-gray-300 text-warning-600 focus:ring-warning-500"
                    />
                    <span className="text-sm text-gray-700">Dry Run Mode (testing only)</span>
                  </label>
                </div>

                <div className="input-group">
                  <label className="input-label">Auto Checkout Keywords</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      className="input-field"
                      value={newKeyword}
                      onChange={(e) => setNewKeyword(e.target.value)}
                      placeholder="e.g., blanton, weller, pappy"
                      onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addKeyword())}
                    />
                    <button
                      type="button"
                      onClick={addKeyword}
                      className="btn btn-primary"
                    >
                      Add
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {config.autoCheckoutKeywords.map((keyword) => (
                      <span
                        key={keyword}
                        className="inline-flex items-center gap-1 px-3 py-1 bg-primary-100 text-primary-800 rounded-full text-sm"
                      >
                        {keyword}
                        <button
                          type="button"
                          onClick={() => removeKeyword(keyword)}
                          className="text-primary-600 hover:text-primary-800"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                <div className="input-group">
                  <label className="input-label">Auto Checkout Events</label>
                  <div className="space-y-2">
                    {['new', 'available'].map((event) => (
                      <label key={event} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={config.autoCheckoutEvents.includes(event)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setConfig(prev => ({
                                ...prev,
                                autoCheckoutEvents: [...prev.autoCheckoutEvents, event]
                              }));
                            } else {
                              setConfig(prev => ({
                                ...prev,
                                autoCheckoutEvents: prev.autoCheckoutEvents.filter(ev => ev !== event)
                              }));
                            }
                          }}
                          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700 capitalize">{event} Products</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Watchlist Settings */}
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-medium text-gray-900">Watchlist</h3>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={config.enableWatchlist}
                  onChange={(e) => setConfig(prev => ({
                    ...prev,
                    enableWatchlist: e.target.checked
                  }))}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-600">Enable</span>
              </label>
            </div>

            {config.enableWatchlist && (
              <div className="space-y-4 pl-4 border-l-2 border-primary-200">
                <div className="input-group">
                  <label className="input-label">Watchlist Product IDs</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      className="input-field font-mono"
                      value={newWatchlistId}
                      onChange={(e) => setNewWatchlistId(e.target.value)}
                      placeholder="Product ID (e.g., 12345)"
                      onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addWatchlistId())}
                    />
                    <button
                      type="button"
                      onClick={addWatchlistId}
                      className="btn btn-primary"
                    >
                      Add
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {config.watchlistIds.map((id) => (
                      <span
                        key={id}
                        className="inline-flex items-center gap-1 px-3 py-1 bg-success-100 text-success-800 rounded-full text-sm font-mono"
                      >
                        {id}
                        <button
                          type="button"
                          onClick={() => removeWatchlistId(id)}
                          className="text-success-600 hover:text-success-800"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <button
            type="submit"
            className={`btn w-full ${isSaved ? 'btn-success' : 'btn-primary'}`}
          >
            <Save className="w-4 h-4" />
            {isSaved ? 'Configuration Saved!' : 'Save Configuration'}
          </button>
        </form>
      </div>
    </div>
  );
};