"use client";

import React, { useState, useRef, forwardRef } from 'react';
import Image from 'next/image';

interface OptimizedImageProps {
  src: string;
  alt: string;
  className?: string;
  style?: React.CSSProperties;
  priority?: boolean;
  onLoad?: () => void;
  fill?: boolean;
  sizes?: string;
  width?: number;
  height?: number;
  silentError?: boolean; // New prop to suppress error UI
}

/**
 * 优化的图片组件
 * - 对于内部 API 路由：使用普通 img（保持兼容性，支持滤镜）
 * - 对于外部图片：使用 Next.js Image（自动优化）
 * - 添加加载状态和错误处理
 */
export const OptimizedImage = forwardRef<HTMLImageElement, OptimizedImageProps>(({
  src,
  alt,
  className = '',
  style = {},
  priority = false,
  onLoad,
  fill = false,
  sizes = '(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw',
  width,
  height,
  silentError = false,
}, ref) => {
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  // 处理图片加载完成
  const handleLoad = () => {
    setIsLoading(false);
    onLoad?.();
  };

  // 处理图片加载错误
  const handleError = () => {
    setHasError(true);
    setIsLoading(false);
  };

  // 判断是否为内部 API 路由
  const isInternalAPI = src.startsWith('/api/');

  // 对于内部 API 路由，使用普通 img 标签（保持原有功能，支持滤镜）
  if (isInternalAPI) {
    return (
      <div className="relative flex items-center justify-center" style={{ width: '100%', height: '100%' }}>
        {isLoading && !hasError && (
          <div className="absolute inset-0 bg-gray-900/50 flex items-center justify-center z-10">
            <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
          </div>
        )}
        <img
          ref={ref}
          src={src}
          alt={alt}
          className={`${className} ${isLoading ? 'opacity-0' : 'opacity-100'} transition-opacity duration-300`}
          style={style}
          onLoad={handleLoad}
          onError={handleError}
          loading={priority ? 'eager' : 'lazy'}
        />
        {hasError && !silentError && (
          <div className="absolute inset-0 bg-gray-900/80 flex items-center justify-center pointer-events-none">
            <span className="text-xs text-gray-500">Failed to load image</span>
          </div>
        )}
      </div>
    );
  }

  // 对于外部图片，使用 Next.js Image 组件进行优化
  if (fill) {
    return (
      <div className="relative" style={{ width: '100%', height: '100%' }}>
        {isLoading && (
          <div className="absolute inset-0 bg-gray-900/50 flex items-center justify-center z-10">
            <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
          </div>
        )}
        <Image
          src={src}
          alt={alt}
          fill
          className={`${className} ${isLoading ? 'opacity-0' : 'opacity-100'} transition-opacity duration-300`}
          style={style}
          priority={priority}
          sizes={sizes}
          onLoad={handleLoad}
          onError={handleError}
          quality={90}
        />
      </div>
    );
  }

  // 固定尺寸的外部图片
  if (width && height) {
    return (
      <div className="relative">
        {isLoading && (
          <div className="absolute inset-0 bg-gray-900/50 flex items-center justify-center z-10">
            <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
          </div>
        )}
        <Image
          src={src}
          alt={alt}
          width={width}
          height={height}
          className={`${className} ${isLoading ? 'opacity-0' : 'opacity-100'} transition-opacity duration-300`}
          style={style}
          priority={priority}
          onLoad={handleLoad}
          onError={handleError}
          quality={90}
        />
      </div>
    );
  }

  // 回退到普通 img
  return (
    <img
      ref={ref}
      src={src}
      alt={alt}
      className={className}
      style={style}
      onLoad={handleLoad}
      onError={handleError}
      loading={priority ? 'eager' : 'lazy'}
    />
  );
});

OptimizedImage.displayName = 'OptimizedImage';
