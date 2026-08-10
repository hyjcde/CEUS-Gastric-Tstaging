"use client";

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

function readUiLanguage(): 'zh' | 'en' {
  if (typeof window === 'undefined') return 'zh';
  const stored = window.localStorage.getItem('gastric_language');
  return stored === 'en' ? 'en' : 'zh';
}

/**
 * Error boundary: catch JS errors in the child tree and show a recovery UI.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({
      error,
      errorInfo,
    });
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const zh = readUiLanguage() !== 'en';

      return (
        <div className="flex items-center justify-center min-h-screen bg-black text-gray-200 p-8">
          <div className="max-w-2xl w-full bg-[#0b0b0d] border border-red-500/30 rounded-xl p-8 shadow-2xl">
            <div className="flex items-start gap-4 mb-6">
              <div className="p-3 bg-red-500/20 rounded-lg border border-red-500/30">
                <AlertTriangle className="text-red-400" size={32} />
              </div>
              <div className="flex-1">
                <h1 className="text-2xl font-bold text-red-400 mb-2">
                  {zh ? '页面出错' : 'Something went wrong'}
                </h1>
                <p className="text-gray-400 text-sm">
                  {zh
                    ? '发生未预期错误。可先点「重试」恢复；若仍失败请刷新页面。'
                    : 'An unexpected error occurred. Try Retry first; if it persists, refresh the page.'}
                </p>
              </div>
            </div>

            {this.state.error ? (
              <div className="mb-6 p-4 bg-black/50 rounded-lg border border-white/10">
                <details className="text-xs font-mono" open>
                  <summary className="cursor-pointer text-gray-400 hover:text-gray-200 mb-2">
                    {zh ? '错误详情（便于排查）' : 'Error details'}
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <span className="text-red-400">Error:</span>
                      <pre className="text-gray-300 mt-1 overflow-auto whitespace-pre-wrap">
                        {this.state.error.toString()}
                      </pre>
                    </div>
                    {this.state.errorInfo?.componentStack ? (
                      <div>
                        <span className="text-red-400">Component stack:</span>
                        <pre className="text-gray-300 mt-1 overflow-auto max-h-40">
                          {this.state.errorInfo.componentStack}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                </details>
              </div>
            ) : null}

            <div className="flex gap-3">
              <button
                onClick={this.handleReset}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
              >
                <RefreshCw size={16} />
                {zh ? '重试' : 'Retry'}
              </button>
              <button
                onClick={this.handleReload}
                className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors font-medium"
              >
                <RefreshCw size={16} />
                {zh ? '刷新页面' : 'Refresh'}
              </button>
              <button
                onClick={this.handleGoHome}
                className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors font-medium"
              >
                <Home size={16} />
                {zh ? '回首页' : 'Home'}
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
