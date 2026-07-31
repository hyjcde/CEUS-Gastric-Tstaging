"use client";

import React from 'react';

/**
 * 通用的 Skeleton 加载组件
 */
export const Skeleton: React.FC<{
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: 'none' | 'sm' | 'md' | 'lg' | 'full';
}> = ({ className = '', width, height, rounded = 'md' }) => {
  const roundedClass = {
    none: '',
    sm: 'rounded-sm',
    md: 'rounded-md',
    lg: 'rounded-lg',
    full: 'rounded-full',
  }[rounded];

  const style: React.CSSProperties = {};
  if (width) style.width = typeof width === 'number' ? `${width}px` : width;
  if (height) style.height = typeof height === 'number' ? `${height}px` : height;

  return (
    <div
      className={`bg-gray-800 animate-pulse ${roundedClass} ${className}`}
      style={style}
    />
  );
};

/**
 * 患者列表项 Skeleton
 */
export const PatientListItemSkeleton: React.FC = () => {
  return (
    <div className="px-3 py-2 border-b border-white/5">
      <div className="flex items-center gap-2">
        <Skeleton width={12} height={12} rounded="full" />
        <Skeleton width={120} height={14} />
        <div className="flex-1" />
        <Skeleton width={40} height={16} rounded="sm" />
      </div>
    </div>
  );
};

/**
 * 患者列表组 Skeleton
 */
export const PatientListGroupSkeleton: React.FC = () => {
  return (
    <div className="bg-[#0b0b0d]">
      <div className="px-3 py-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Skeleton width={12} height={12} />
          <Skeleton width={100} height={14} />
          <div className="flex-1" />
          <Skeleton width={50} height={16} rounded="sm" />
        </div>
      </div>
      <div className="bg-[#08080a] pl-8">
        {[...Array(3)].map((_, i) => (
          <PatientListItemSkeleton key={i} />
        ))}
      </div>
    </div>
  );
};

/**
 * 图片加载 Skeleton
 */
export const ImageSkeleton: React.FC<{ aspectRatio?: string }> = ({ aspectRatio = 'auto' }) => {
  return (
    <div className="relative w-full h-full flex items-center justify-center bg-black">
      <div className="absolute inset-0 bg-gray-900 animate-pulse" />
      <div className="relative z-10 flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
        <Skeleton width={100} height={12} />
      </div>
    </div>
  );
};

/**
 * 诊断面板 Skeleton
 */
export const DiagnosisPanelSkeleton: React.FC = () => {
  return (
    <div className="flex flex-col h-full bg-bg-dark">
      <div className="h-9 shrink-0 border-b border-neutral-800 flex items-center justify-between px-3">
        <Skeleton width={80} height={16} />
        <Skeleton width={16} height={16} rounded="full" />
      </div>
      <div className="flex-1 p-4 space-y-4">
        <div className="space-y-2">
          <Skeleton width={60} height={12} />
          <Skeleton width="100%" height={8} />
          <Skeleton width="80%" height={8} />
          <Skeleton width="90%" height={8} />
        </div>
        <div className="space-y-2">
          <Skeleton width={60} height={12} />
          <Skeleton width="100%" height={8} />
          <Skeleton width="75%" height={8} />
        </div>
        <div className="space-y-2">
          <Skeleton width={60} height={12} />
          <Skeleton width="100%" height={60} rounded="md" />
        </div>
      </div>
    </div>
  );
};

/**
 * 概念推理面板 Skeleton
 */
export const ConceptReasoningSkeleton: React.FC = () => {
  return (
    <div className="flex flex-col h-full bg-panel-bg">
      <div className="h-9 shrink-0 border-b border-white/5 flex items-center justify-between px-4">
        <Skeleton width={150} height={14} />
        <Skeleton width={16} height={16} rounded="full" />
      </div>
      <div className="flex-1 p-3 space-y-4">
        <Skeleton width="100%" height={120} rounded="lg" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-between">
              <Skeleton width={60} height={12} />
              <Skeleton width={40} height={12} />
            </div>
            <Skeleton width="100%" height={4} rounded="full" />
          </div>
        ))}
      </div>
    </div>
  );
};

