import React, { useState, useEffect } from 'react';
import { Tag, Plus, Edit2, Trash2, Save, X } from 'lucide-react';
import { KeywordRule } from '../types';
import { storage } from '../utils/storage';

export const KeywordManager: React.FC = () => {
  const [rules, setRules] = useState<KeywordRule[]>([]);
  const [editingRule, setEditingRule] = useState<KeywordRule | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    const savedRules = storage.getKeywordRules();
    setRules(savedRules);
  }, []);

  const saveRules = (newRules: KeywordRule[]) => {
    setRules(newRules);
    storage.setKeywordRules(newRules);
  };

  const createNewRule = (): KeywordRule => ({
    id: Date.now().toString(),
    name: '',
    keywords: [],
    matchMode: 'any',
    searchFields: ['name', 'page_url'],
    enabled: true,
    description: ''
  });

  const handleCreateRule = () => {
    const newRule = createNewRule();
    setEditingRule(newRule);
    setIsCreating(true);
  };

  const handleSaveRule = (rule: KeywordRule) => {
    if (isCreating) {
      saveRules([...rules, rule]);
      setIsCreating(false);
    } else {
      saveRules(rules.map(r => r.id === rule.id ? rule : r));
    }
    setEditingRule(null);
  };

  const handleDeleteRule = (ruleId: string) => {
    if (confirm('Are you sure you want to delete this keyword rule?')) {
      saveRules(rules.filter(r => r.id !== ruleId));
    }
  };

  const handleToggleRule = (ruleId: string) => {
    saveRules(rules.map(r => 
      r.id === ruleId ? { ...r, enabled: !r.enabled } : r
    ));
  };

  const handleCancelEdit = () => {
    setEditingRule(null);
    setIsCreating(false);
  };

  return (
    <div className="card">
      <div className="card-header">
        <Tag className="w-6 h-6 text-primary-600" />
        <div className="flex-1">
          <h2 className="text-xl font-semibold text-gray-900">Keyword Rules</h2>
          <p className="text-sm text-gray-600">Create advanced keyword matching rules for products</p>
        </div>
        <button
          onClick={handleCreateRule}
          className="btn btn-primary"
        >
          <Plus className="w-4 h-4" />
          Add Rule
        </button>
      </div>

      <div className="space-y-4">
        {rules.length === 0 && !editingRule && (
          <div className="text-center py-8 text-gray-500">
            <Tag className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p>No keyword rules configured yet.</p>
            <p className="text-sm">Create your first rule to get started.</p>
          </div>
        )}

        {rules.map((rule) => (
          <div key={rule.id}>
            {editingRule?.id === rule.id ? (
              <KeywordRuleEditor
                rule={editingRule}
                onSave={handleSaveRule}
                onCancel={handleCancelEdit}
              />
            ) : (
              <KeywordRuleCard
                rule={rule}
                onEdit={() => setEditingRule(rule)}
                onDelete={() => handleDeleteRule(rule.id)}
                onToggle={() => handleToggleRule(rule.id)}
              />
            )}
          </div>
        ))}

        {editingRule && isCreating && (
          <KeywordRuleEditor
            rule={editingRule}
            onSave={handleSaveRule}
            onCancel={handleCancelEdit}
          />
        )}
      </div>
    </div>
  );
};

interface KeywordRuleCardProps {
  rule: KeywordRule;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
}

const KeywordRuleCard: React.FC<KeywordRuleCardProps> = ({ rule, onEdit, onDelete, onToggle }) => {
  return (
    <div className={`border rounded-lg p-4 ${rule.enabled ? 'border-gray-200 bg-white' : 'border-gray-100 bg-gray-50'}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h3 className={`font-medium ${rule.enabled ? 'text-gray-900' : 'text-gray-500'}`}>
              {rule.name || 'Unnamed Rule'}
            </h3>
            <span className={`status-indicator ${rule.enabled ? 'status-running' : 'status-stopped'}`}>
              {rule.enabled ? 'Active' : 'Disabled'}
            </span>
          </div>
          
          {rule.description && (
            <p className="text-sm text-gray-600 mb-3">{rule.description}</p>
          )}
          
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1">
              {rule.keywords.map((keyword, index) => (
                <span
                  key={index}
                  className="inline-flex items-center px-2 py-1 bg-primary-100 text-primary-800 rounded text-xs"
                >
                  {keyword}
                </span>
              ))}
            </div>
            
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span>Match: <strong>{rule.matchMode}</strong></span>
              <span>Fields: <strong>{rule.searchFields.join(', ')}</strong></span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={onToggle}
            className={`btn ${rule.enabled ? 'btn-warning' : 'btn-success'} text-xs`}
          >
            {rule.enabled ? 'Disable' : 'Enable'}
          </button>
          <button
            onClick={onEdit}
            className="btn btn-secondary text-xs"
          >
            <Edit2 className="w-3 h-3" />
          </button>
          <button
            onClick={onDelete}
            className="btn btn-error text-xs"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
};

interface KeywordRuleEditorProps {
  rule: KeywordRule;
  onSave: (rule: KeywordRule) => void;
  onCancel: () => void;
}

const KeywordRuleEditor: React.FC<KeywordRuleEditorProps> = ({ rule, onSave, onCancel }) => {
  const [editedRule, setEditedRule] = useState<KeywordRule>(rule);
  const [newKeyword, setNewKeyword] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editedRule.name.trim()) {
      alert('Please enter a rule name');
      return;
    }
    if (editedRule.keywords.length === 0) {
      alert('Please add at least one keyword');
      return;
    }
    onSave(editedRule);
  };

  const addKeyword = () => {
    if (newKeyword.trim() && !editedRule.keywords.includes(newKeyword.trim().toLowerCase())) {
      setEditedRule(prev => ({
        ...prev,
        keywords: [...prev.keywords, newKeyword.trim().toLowerCase()]
      }));
      setNewKeyword('');
    }
  };

  const removeKeyword = (keyword: string) => {
    setEditedRule(prev => ({
      ...prev,
      keywords: prev.keywords.filter(k => k !== keyword)
    }));
  };

  const toggleSearchField = (field: string) => {
    setEditedRule(prev => ({
      ...prev,
      searchFields: prev.searchFields.includes(field)
        ? prev.searchFields.filter(f => f !== field)
        : [...prev.searchFields, field]
    }));
  };

  return (
    <div className="border border-primary-200 rounded-lg p-4 bg-primary-50">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="input-group">
            <label className="input-label">Rule Name</label>
            <input
              type="text"
              className="input-field"
              value={editedRule.name}
              onChange={(e) => setEditedRule(prev => ({ ...prev, name: e.target.value }))}
              placeholder="e.g., Premium Bourbon"
              required
            />
          </div>
          
          <div className="input-group">
            <label className="input-label">Match Mode</label>
            <select
              className="input-field"
              value={editedRule.matchMode}
              onChange={(e) => setEditedRule(prev => ({ ...prev, matchMode: e.target.value as 'any' | 'all' }))}
            >
              <option value="any">Any keyword matches</option>
              <option value="all">All keywords must match</option>
            </select>
          </div>
        </div>

        <div className="input-group">
          <label className="input-label">Description (optional)</label>
          <textarea
            className="input-field"
            value={editedRule.description || ''}
            onChange={(e) => setEditedRule(prev => ({ ...prev, description: e.target.value }))}
            placeholder="Describe what this rule is for..."
            rows={2}
          />
        </div>

        <div className="input-group">
          <label className="input-label">Keywords</label>
          <div className="flex gap-2">
            <input
              type="text"
              className="input-field"
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              placeholder="Enter keyword..."
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
            {editedRule.keywords.map((keyword) => (
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
          <label className="input-label">Search Fields</label>
          <div className="space-y-2">
            {['name', 'page_url', 'id'].map((field) => (
              <label key={field} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={editedRule.searchFields.includes(field)}
                  onChange={() => toggleSearchField(field)}
                  className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700 capitalize">
                  {field === 'page_url' ? 'Product URL' : field}
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            className="btn btn-success"
          >
            <Save className="w-4 h-4" />
            Save Rule
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="btn btn-secondary"
          >
            <X className="w-4 h-4" />
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
};