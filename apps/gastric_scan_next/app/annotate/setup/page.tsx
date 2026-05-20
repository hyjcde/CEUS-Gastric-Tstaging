"use client";

import React, { useState, useEffect, useRef } from "react";

declare global {
  interface Window {
    electronAPI?: {
      selectFolder: () => Promise<string | null>;
      getDataRoot: () => Promise<string | null>;
      setDataRoot: (path: string) => Promise<boolean>;
    };
  }
}

export default function SetupPage() {
  const [dataRoot, setDataRoot] = useState<string | null>(null);
  const [projectRoot, setProjectRoot] = useState<string | null>(null);
  const [datasetDir, setDatasetDir] = useState<string | null>(null);
  const [batchExists, setBatchExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [manualPath, setManualPath] = useState("");
  const [isElectron, setIsElectron] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setIsElectron(!!window.electronAPI);
    checkConfig();
  }, []);

  const checkConfig = async () => {
    try {
      const res = await fetch("/api/direction-annotation/config");
      const data = await res.json();
      setDataRoot(data.data_root || null);
      setProjectRoot(data.project_root || null);
      setDatasetDir(data.dataset_dir || null);
      setBatchExists(data.batch_exists || false);
      if (data.data_root) setManualPath(data.data_root);
      if (data.batch_exists) {
        window.location.href = "/annotate";
        return;
      }
    } catch {
      setError("无法连接到服务");
    } finally {
      setLoading(false);
    }
  };

  const handleElectronBrowse = async () => {
    if (!window.electronAPI) return;
    const folder = await window.electronAPI.selectFolder();
    if (folder) {
      setManualPath(folder);
      await applyPath(folder);
    }
  };

  const applyPath = async (p: string) => {
    if (!p.trim()) return;
    setApplying(true);
    setError(null);
    setSuccess(null);
    try {
      if (window.electronAPI) {
        await window.electronAPI.setDataRoot(p);
      }
      const res = await fetch("/api/direction-annotation/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data_root: p }),
      });
      const data = await res.json();
      if (!data.success) {
        setError(data.error || "设置失败");
        return;
      }
      setDataRoot(p);

      const check = await fetch("/api/direction-annotation/config");
      const checkData = await check.json();
      setProjectRoot(checkData.project_root || null);
      setDatasetDir(checkData.dataset_dir || null);
      setBatchExists(checkData.batch_exists);

      if (checkData.batch_exists) {
        setSuccess("已找到标注批次文件，正在跳转...");
        setTimeout(() => { window.location.href = "/annotate"; }, 600);
      } else {
        setError(
          "该目录下未找到 direction_annotation_batch.json 文件。\n" +
          "请确认选择了正确的数据集根目录。"
        );
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setApplying(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <div className="text-sm text-gray-400">正在检查配置...</div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-screen px-4">
      <div className="max-w-xl w-full space-y-5">
        {/* Header */}
        <div className="text-center space-y-1">
          <div className="text-3xl mb-2">🔬</div>
          <h1 className="text-xl font-bold tracking-tight">突破方向标注工具</h1>
          <p className="text-xs text-gray-500">胃癌 EUS 超声内镜 — 肿瘤突破方向标注</p>
        </div>

        {/* Main card */}
        <div className="bg-[#0d1117] border border-gray-800 rounded-xl p-5 space-y-4">
          <div className="text-sm font-medium text-gray-300">设置数据集目录</div>
          <div className="text-xs text-gray-500 leading-relaxed">
            默认会优先使用当前工程下的 <code className="text-gray-300 bg-gray-800 px-1 rounded">dataset</code> 文件夹。
            你也可以直接选择 <code className="text-gray-300 bg-gray-800 px-1 rounded">dataset</code>，程序会自动识别对应的项目根目录。
          </div>

          {/* Current data root display */}
          {(dataRoot || projectRoot || datasetDir) && (
            <div className="text-xs text-gray-500 bg-gray-900/50 rounded px-3 py-2 space-y-1 font-mono break-all">
              {dataRoot && <div>当前选择: {dataRoot}</div>}
              {datasetDir && <div>数据目录: {datasetDir}</div>}
              {projectRoot && <div>项目根目录: {projectRoot}</div>}
            </div>
          )}

          {/* Electron browse button */}
          {isElectron && (
            <button
              onClick={handleElectronBrowse}
              disabled={applying}
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg font-medium transition-colors text-sm flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              浏览选择数据集目录...
            </button>
          )}

          {/* Path input */}
          <div className="space-y-2">
            {isElectron && <div className="text-center text-[10px] text-gray-600">— 或手动输入路径 —</div>}
            {datasetDir && (
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    setManualPath(datasetDir);
                    inputRef.current?.focus();
                  }}
                  className="px-2.5 py-1 text-[11px] bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-md transition-colors"
                >
                  使用默认 dataset
                </button>
                {projectRoot && (
                  <button
                    onClick={() => {
                      setManualPath(projectRoot);
                      inputRef.current?.focus();
                    }}
                    className="px-2.5 py-1 text-[11px] bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-md transition-colors"
                  >
                    使用项目根目录
                  </button>
                )}
              </div>
            )}
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                placeholder={isElectron ? "D:\\gastric_data\\dataset 或 D:\\gastric_data" : "/data/research/gastric/GastricTstaging 或 /data/research/gastric/GastricTstaging/dataset"}
                className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-sm font-mono placeholder-gray-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all"
                onKeyDown={(e) => { if (e.key === "Enter" && manualPath.trim()) applyPath(manualPath.trim()); }}
                autoFocus={!isElectron}
              />
              <button
                onClick={() => manualPath.trim() && applyPath(manualPath.trim())}
                disabled={!manualPath.trim() || applying}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-30 disabled:hover:bg-blue-600 rounded-lg text-sm font-medium transition-colors shrink-0"
              >
                {applying ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  "确认"
                )}
              </button>
            </div>
          </div>

          {/* Status messages */}
          {error && (
            <div className="text-sm text-red-400 bg-red-950/30 border border-red-900/40 rounded-lg px-4 py-3 whitespace-pre-line">
              {error}
            </div>
          )}
          {success && (
            <div className="text-sm text-green-400 bg-green-950/30 border border-green-900/40 rounded-lg px-4 py-3 flex items-center gap-2">
              <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/>
              </svg>
              {success}
            </div>
          )}

          {/* Direct annotate link */}
          {batchExists && (
            <a
              href="/annotate"
              className="block text-center py-3 bg-green-700 hover:bg-green-600 rounded-lg font-medium transition-colors text-sm"
            >
              开始标注 →
            </a>
          )}
        </div>

        {/* Help card */}
        <details className="bg-[#0d1117] border border-gray-800 rounded-xl">
          <summary className="px-5 py-3 text-xs text-gray-400 cursor-pointer hover:text-gray-300 transition-colors select-none">
            数据目录要求 & 帮助
          </summary>
          <div className="px-5 pb-4 text-xs text-gray-500 space-y-2 border-t border-gray-800 pt-3">
            <div className="font-mono text-[11px] text-gray-400 bg-gray-900/50 rounded p-3 leading-relaxed">
              项目根目录/<br/>
              ├── direction_annotation_batch.json &nbsp;<span className="text-yellow-500">← 必需</span><br/>
              ├── dataset/ &nbsp;<span className="text-yellow-500">← 必需，包含图像</span><br/>
              │ &nbsp;&nbsp;├── internal/<br/>
              │ &nbsp;&nbsp;└── external/<br/>
              └── direction_annotations/ &nbsp;<span className="text-gray-600">← 自动创建</span>
            </div>
            <p>支持两种选择方式：直接选择 <code className="text-gray-300 bg-gray-800 px-1 rounded">dataset</code> 文件夹，或选择它的上一级项目根目录。</p>
            <p>如没有 <code className="text-gray-300 bg-gray-800 px-1 rounded">direction_annotation_batch.json</code>，请联系研究人员生成。</p>
          </div>
        </details>

        <div className="text-center text-[10px] text-gray-700">v1.0.0 · 福建医科大学附属协和医院</div>
      </div>
    </div>
  );
}
