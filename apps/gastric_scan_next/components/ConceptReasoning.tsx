"use client";

import { CONCEPT_CONFIGS, getConceptBarGradient } from '@/lib/medical-config';
import { ConceptFieldSource, ConceptFieldSources } from '@/lib/concept-agent-merge';
import { ConceptState } from '@/types';
import { Activity, RotateCcw, Save, ShieldAlert, Sliders } from 'lucide-react';
import React from 'react';
import { useSettings } from '@/contexts/SettingsContext';
import { RadarChart } from './RadarChart';

interface ConceptReasoningProps {
  state: ConceptState;
  onChange: (key: keyof ConceptState, value: number) => void;
  onReset?: () => void;
  onSave?: () => void;
  populatedCount?: number;
  agentFilledCount?: number;
  fieldSources?: ConceptFieldSources;
  hasClinicalData?: boolean;
  isDirty?: boolean;
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error';
  autoSaveEnabled?: boolean;
}

export const ConceptReasoning: React.FC<ConceptReasoningProps> = React.memo(({
  state,
  onChange,
  onReset,
  onSave,
  populatedCount = 0,
  agentFilledCount = 0,
  fieldSources,
  hasClinicalData = false,
  isDirty = false,
  saveStatus = 'idle',
  autoSaveEnabled = false,
}) => {
  const { t, language } = useSettings();

  const sourceMeta = (source?: ConceptFieldSource) => {
    if (!source || source === 'default') return null;
    if (source === 'clinical') {
      return { label: language !== 'en' ? '病理' : 'PATH', className: 'text-emerald-400/90 border-emerald-500/30 bg-emerald-500/10' };
    }
    if (source === 'agent') {
      return { label: language !== 'en' ? 'Agent' : 'AGT', className: 'text-purple-400/90 border-purple-500/30 bg-purple-500/10' };
    }
    return { label: language !== 'en' ? '手动' : 'EDIT', className: 'text-amber-400/90 border-amber-500/30 bg-amber-500/10' };
  };

  const renderSourceBadge = (key: keyof ConceptState) => {
    const meta = sourceMeta(fieldSources?.[key]);
    if (!meta) return null;
    return (
      <span className={`ml-1 px-1 py-0 rounded border text-[7px] font-bold uppercase tracking-wide ${meta.className}`}>
        {meta.label}
      </span>
    );
  };
  
  const renderSlider = (key: keyof ConceptState) => {
    const config = CONCEPT_CONFIGS[key as string];
    if (!config) return null; // Should not happen for configured keys

    // Ensure val is never undefined to avoid uncontrolled input warning
    const val = state[key] ?? 50;
    
    // Dynamic color logic from config
    const barGradient = getConceptBarGradient(val, config.thresholds);

    return (
      <div className="group py-1.5">
        <div className="flex justify-between items-end mb-1.5">
          <span className="text-[10px] font-bold text-gray-400 group-hover:text-gray-200 transition-colors uppercase tracking-tight">
            {config.label[language as 'zh' | 'en']}
            {renderSourceBadge(key)}
          </span>
          <div className="flex items-baseline gap-1">
             <span className={`text-[10px] font-mono font-bold ${val > config.thresholds.warning ? 'text-gray-100' : 'text-gray-500'}`}>{val}%</span>
          </div>
        </div>
        
        <div className="relative h-3 flex items-center select-none mb-1">
           <input 
            type="range" 
            min="0" 
            max="100" 
            value={val}
            onChange={(e) => onChange(key, parseInt(e.target.value))}
            className="z-20 opacity-0 w-full h-full absolute cursor-pointer"
          />
          {/* Track Background */}
          <div className="w-full h-1 bg-[#1a1a1a] rounded-full overflow-hidden relative shadow-inner border border-border-col">
             {/* Fill */}
             <div 
               className={`h-full bg-linear-to-r ${barGradient} transition-all duration-300 ease-out opacity-90 group-hover:opacity-100`} 
               style={{ width: `${val}%` }}
             ></div>
          </div>
          
          {/* Thumb (Visual Only) */}
          <div 
            className="absolute h-2.5 w-2.5 bg-[#e4e4e7] rounded-full shadow-[0_2px_5px_rgba(0,0,0,0.5)] border border-border-col pointer-events-none transition-all duration-75 ease-out group-hover:scale-110"
            style={{ left: `calc(${val}% - 5px)` }}
          ></div>
        </div>
        
        {/* Labels */}
        <div className="flex justify-between text-[8px] text-gray-600 font-mono uppercase">
            <span>{config.minLabel}</span>
            <span>{config.maxLabel}</span>
        </div>
      </div>
    );
  };

  const renderSelect = (
    key: keyof ConceptState,
    label: string,
    options: { value: number; label: string }[]
  ) => {
    // Ensure val is never undefined
    const val = state[key] ?? options[0]?.value ?? 0;

    return (
      <div className="py-2 border-t border-white/5">
        <div className="text-[10px] font-bold text-gray-400 mb-2 uppercase tracking-tight">
          {label}
          {renderSourceBadge(key)}
        </div>
        <div className="grid grid-cols-1 gap-1">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onChange(key, opt.value)}
              className={`text-[10px] py-1.5 px-2 rounded border transition-all text-left flex items-center justify-between ${
                val === opt.value
                  ? "bg-blue-500/20 text-blue-400 border-blue-500/40 shadow-[0_0_10px_rgba(59,130,246,0.15)]"
                  : "bg-white/5 text-gray-500 border-white/5 hover:border-white/10 hover:bg-white/10"
              }`}
            >
              <span>{opt.label}</span>
              {val === opt.value && <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shadow-[0_0_5px_currentColor]"></div>}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderToggle = (key: keyof ConceptState, label: string) => {
    // Ensure val is never undefined
    const val = state[key] ?? 0;

    return (
      <div className="py-2 flex items-center justify-between border-t border-white/5">
        <span className="text-[10px] font-bold text-gray-400 uppercase tracking-tight">
          {label}
          {renderSourceBadge(key)}
        </span>
        <div className="flex bg-black/40 rounded-lg p-0.5 border border-white/5">
          <button
            onClick={() => onChange(key, 0)}
            className={`px-3 py-1 rounded-md text-[9px] font-bold transition-all ${
              val === 0
                ? "bg-gray-700 text-gray-200 shadow-sm"
                : "text-gray-600 hover:text-gray-400"
            }`}
          >
            {language !== 'en' ? '无' : 'NO'}
          </button>
          <button
            onClick={() => onChange(key, 1)}
            className={`px-3 py-1 rounded-md text-[9px] font-bold transition-all ${
              val === 1
                ? "bg-red-500/80 text-white shadow-[0_0_10px_rgba(239,68,68,0.3)]"
                : "text-gray-600 hover:text-gray-400"
            }`}
          >
            {language !== 'en' ? '有' : 'YES'}
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full w-full bg-panel-bg">
      <div className="h-9 shrink-0 border-b border-white/5 flex items-center justify-between px-4 bg-panel-bg">
        <span className="flex items-center gap-2 text-[11px] font-bold text-gray-300 uppercase tracking-widest">
          <Sliders size={12} className="text-blue-500" /> 
          {language !== 'en' ? '病理特征推理 (CBM)' : 'Pathology CBM Reasoning'}
        </span>
        <div className="flex items-center gap-2">
          {onSave && (
            <button
              onClick={onSave}
              disabled={saveStatus === 'saving'}
              className={`flex items-center gap-1 text-[9px] px-2 py-0.5 rounded border transition-colors ${
                saveStatus === 'saved'
                  ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                  : isDirty
                    ? 'border-blue-500/40 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20'
                    : 'border-white/10 text-gray-500 hover:text-gray-300'
              }`}
              title={language !== 'en' ? '保存当前 CBM 调整' : 'Save CBM adjustments'}
            >
              <Save size={10} />
              {saveStatus === 'saving'
                ? (language !== 'en' ? '保存中' : 'Saving')
                : saveStatus === 'saved'
                  ? (language !== 'en' ? '已保存' : 'Saved')
                  : saveStatus === 'error'
                    ? (language !== 'en' ? '失败' : 'Failed')
                    : (language !== 'en' ? '保存' : 'Save')}
            </button>
          )}
          <button onClick={onReset} className="text-gray-600 hover:text-white transition-colors" title="Reset">
            <RotateCcw size={12} />
          </button>
        </div>
      </div>

      <div className="px-4 py-1.5 border-b border-white/5 bg-[#101014] text-[9px] text-gray-500 flex items-center justify-between gap-2">
        <span className="truncate">
          {hasClinicalData
            ? (language !== 'en'
              ? `病理/IHC ${populatedCount > 0 ? `${populatedCount} 项` : '已载入'}`
              : `Pathology/IHC ${populatedCount > 0 ? `(${populatedCount})` : 'loaded'}`)
            : (language !== 'en' ? '无临床数据，显示默认值' : 'No clinical data, defaults')}
          {agentFilledCount > 0 && (
            <span className="text-purple-400 ml-1">
              {language !== 'en' ? `· Agent/超声 +${agentFilledCount}` : `· Agent/US +${agentFilledCount}`}
            </span>
          )}
          {autoSaveEnabled && isDirty && saveStatus === 'idle' && (
            <span className="text-blue-400 ml-1">
              {language !== 'en' ? '· 待自动保存' : '· pending autosave'}
            </span>
          )}
        </span>
        <span className="font-mono text-gray-600 shrink-0">
          Ki67 {state.c1}% · CPS {state.c2}
        </span>
      </div>
      
      <div className="flex-1 overflow-y-auto min-h-0 p-3 custom-scrollbar space-y-4">
        {/* Radar Chart Section */}
        <div className="border-b border-white/5 pb-4 flex justify-center">
           <div className="w-[80%]">
           <RadarChart 
              data={[state.c1 ?? 50, state.c2 ?? 50, state.c3 ?? 50, state.c4 ?? 50]} 
              labels={[
                  CONCEPT_CONFIGS.c1.label[language as 'zh' | 'en'], 
                  CONCEPT_CONFIGS.c2.label[language as 'zh' | 'en'], 
                  CONCEPT_CONFIGS.c3.label[language as 'zh' | 'en'], 
                  CONCEPT_CONFIGS.c4.label[language as 'zh' | 'en']
              ]}
              color={(state.c1 ?? 50) > CONCEPT_CONFIGS.c1.thresholds.danger ? '#ef4444' : '#3b82f6'}
           />
           </div>
        </div>

        {/* IHC Markers */}
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-blue-400/80 uppercase tracking-wider">
             <Activity size={10} />
             {language !== 'en' ? '免疫组化 (IHC)' : 'IHC Markers'}
          </div>
          {renderSlider('c1')}
          {renderSlider('c2')}
          {renderSlider('c3')}
          {renderSlider('c4')}
        </div>

        {/* TME Markers */}
        <div className="space-y-1 pt-2 border-t border-white/5">
          <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-emerald-400/80 uppercase tracking-wider">
             <Activity size={10} />
             {language !== 'en' ? '免疫微环境 (TME)' : 'TME Status'}
          </div>
          {renderSlider('c5')}
          {renderSlider('c6')}
          {renderSlider('c7')}
        </div>

        {/* Pathology Type & Invasion */}
        <div className="space-y-1 pt-2 border-t border-white/5">
          <div className="flex items-center gap-1.5 mb-2 text-[10px] font-bold text-purple-400/80 uppercase tracking-wider">
             <ShieldAlert size={10} />
             {language !== 'en' ? '病理分型 & 侵犯' : 'Type & Invasion'}
          </div>
          
          {renderSelect("differentiation", language !== 'en' ? "分化程度" : "Differentiation", [
            { value: 1, label: language !== 'en' ? "1: 高分化 (Well)" : "1: Well Diff" },
            { value: 2, label: language !== 'en' ? "2: 中分化 (Mod)" : "2: Mod Diff" },
            { value: 3, label: language !== 'en' ? "3: 中-低分化" : "3: Mod-Poor" },
            { value: 4, label: language !== 'en' ? "4: 低分化 (Poor)" : "4: Poorly Diff" },
            { value: 5, label: language !== 'en' ? "5: 不确定" : "5: Unknown" },
          ])}

          {renderSelect("lauren", "Lauren 分型", [
            { value: 1, label: language !== 'en' ? "1: 肠型 (Intestinal)" : "1: Intestinal" },
            { value: 0, label: language !== 'en' ? "0: 弥漫型 (Diffuse)" : "0: Diffuse" },
            { value: 4, label: language !== 'en' ? "4: 混合/不确定" : "4: Mixed/Unk" },
          ])}

          {renderToggle("vascularInvasion", language !== 'en' ? "脉管侵犯 (LVI)" : "Vascular Inv")}
          {renderToggle("neuralInvasion", language !== 'en' ? "神经侵犯 (PNI)" : "Neural Inv")}
        </div>
      </div>
    </div>
  );
});

ConceptReasoning.displayName = 'ConceptReasoning';
