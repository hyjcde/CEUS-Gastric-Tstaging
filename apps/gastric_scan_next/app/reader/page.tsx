'use client';

import React, { Suspense, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { ReaderWorkbench } from '@/components/reader/ReaderWorkbench';

function ReaderLoadingFallback() {
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setTimedOut(true), 8000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[#08090a] text-gray-400">
      <Loader2 className="animate-spin" size={24} />
      <div className="text-xs">Loading the reading workbench…</div>
      {timedOut ? (
        <div className="flex flex-col items-center gap-2 text-center text-[11px] text-amber-300">
          <div>The page is taking longer than expected. Retry; case data will not be modified.</div>
          <button type="button" className="reader-btn" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function ReaderPage() {
  return (
    <Suspense fallback={<ReaderLoadingFallback />}>
      <ReaderWorkbench />
    </Suspense>
  );
}
