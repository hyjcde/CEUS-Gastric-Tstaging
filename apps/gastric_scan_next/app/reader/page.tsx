'use client';

import React, { Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import { ReaderWorkbench } from '@/components/reader/ReaderWorkbench';

export default function ReaderPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-[#08090a] text-gray-400">
          <Loader2 className="animate-spin" size={24} />
        </div>
      }
    >
      <ReaderWorkbench />
    </Suspense>
  );
}
