"use client";

import React, { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Patient } from '@/types';
import { Search, Database, ChevronDown, ChevronRight, Folder, FileImage } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import toast from 'react-hot-toast';
import { PatientListGroupSkeleton } from './Skeleton';

interface PatientListProps {
  onSelect: (patient: Patient) => void;
  selectedId: string | null;
  onPatientsLoaded?: (patients: Patient[]) => void;
}

// Helper type for grouped patients
interface PatientGroup {
  baseId: string; // e.g., 1MC_1424711
  groupType: string; // Chemo/Surgery
  items: Patient[];
}

export const PatientList: React.FC<PatientListProps> = ({ onSelect, selectedId, onPatientsLoaded }) => {
  const { dataset, cohortYear, t } = useSettings();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [displayLimit, setDisplayLimit] = useState(50);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isLoadingMore = useRef(false);
  const onSelectRef = useRef(onSelect);
  const onPatientsLoadedRef = useRef(onPatientsLoaded);
  const selectedIdRef = useRef(selectedId);
  const hasAutoSelectedRef = useRef(false);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    onPatientsLoadedRef.current = onPatientsLoaded;
  }, [onPatientsLoaded]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    let isMounted = true;

    const safeFetchPatients = async (treatment: 'surgery' | 'nac'): Promise<Patient[]> => {
      try {
        const response = await fetch(`/api/patients?dataset=${dataset}&cohort=${cohortYear}&treatment=${treatment}`);
        if (!response.ok) {
          console.warn(`Fetch ${treatment} patients failed (${response.status})`);
          return [];
        }
        const data = await response.json();
        if (!Array.isArray(data)) {
          console.warn(`Unexpected ${treatment} payload`, data);
          return [];
        }
        return data;
      } catch (error) {
        console.error(`Failed to load ${treatment} data`, error);
        toast.error(`Failed to load ${treatment} patient data`);
        return [];
      }
    };

    const loadPatients = async () => {
      setLoading(true);
      setDisplayLimit(50);

      // gist数据集不支持NAC，只请求surgery数据
      const shouldFetchNac = cohortYear !== 'gist';
      const [surgeryData, nacData] = await Promise.all([
        safeFetchPatients('surgery'),
        shouldFetchNac ? safeFetchPatients('nac') : Promise.resolve([])
      ]);

      if (!isMounted) return;

      // Merge both datasets (nacData might be empty for years without NAC)
      const allData = [...surgeryData, ...nacData];
      const seen = new Set<string>();
      const merged = allData.filter(p => {
        if (seen.has(p.id)) {
          console.warn(`Duplicate patient ID found: ${p.id}, skipping duplicate`);
          return false;
        }
        seen.add(p.id);
        return true;
      });

      setPatients(merged);
      setLoading(false);
      onPatientsLoadedRef.current?.(merged);

      const currentSelectedId = selectedIdRef.current;

      // Auto-expand the group of the selected patient if exists
      if (currentSelectedId) {
          const p = merged.find((x: Patient) => x.id === currentSelectedId);
          if (p) {
              const patientId = p.patient_id || p.id_short.split('(')[0].trim();
              const isNAC = p.group === 'NAC' || p.id.startsWith('NAC_');
              const treatmentType = isNAC ? 'NAC' : 'Surgery';
              const groupKey = `${patientId}_${treatmentType}`;
              setExpandedGroups(new Set([groupKey]));
          }
      } else if (merged.length > 0 && !hasAutoSelectedRef.current) {
          hasAutoSelectedRef.current = true;
          onSelectRef.current(merged[0]);
          const patientId = merged[0].patient_id || merged[0].id_short.split('(')[0].trim();
          const isNAC = merged[0].group === 'NAC' || merged[0].id.startsWith('NAC_');
          const treatmentType = isNAC ? 'NAC' : 'Surgery';
          const groupKey = `${patientId}_${treatmentType}`;
          setExpandedGroups(new Set([groupKey]));
      }
    };

    loadPatients().catch(error => {
      console.error('Failed to load patients', error);
      if (isMounted) {
        setLoading(false);
        toast.error('Failed to load patient list. Please refresh the page.');
      }
    });

    return () => {
      isMounted = false;
    };
  }, [dataset, cohortYear]);

  useEffect(() => {
    hasAutoSelectedRef.current = false;
  }, [dataset, cohortYear]);

  // Grouping Logic - Group by patient_id and treatment type
  const groupedPatients = useMemo(() => {
    const groups: Record<string, PatientGroup> = {};
    
    patients.forEach(p => {
        // Use patient_id for grouping (this is the actual patient ID from Excel)
        // For 2019: patient_id is extracted from filename (e.g., "127" from "1-127-3")
        // For 2025: patient_id is the numeric ID (e.g., "1424711")
        const patientId = p.patient_id || p.id_short.split('(')[0].trim();
        
        // Determine treatment type: NAC files start with "NAC_", Surgery files start with "Surgery_"
        const isNAC = p.group === 'NAC' || p.id.startsWith('NAC_');
        const treatmentType = isNAC ? 'NAC' : 'Surgery';
        
        // Create a unique key: patientId + treatmentType (so same patient can have both Surgery and NAC)
        const baseId = `${patientId}_${treatmentType}`;
        
        if (!groups[baseId]) {
            groups[baseId] = {
                baseId: patientId, // Display patient ID (without treatment suffix)
                groupType: treatmentType, // 'NAC' or 'Surgery'
                items: []
            };
        }
        groups[baseId].items.push(p);
    });

    // Sort groups: first by clinical data presence (any item in group has clinical), then by patient_id, then by treatment type
    const sortedGroups = Object.values(groups).sort((a, b) => {
        // 1. Clinical data presence
        const hasClinicalA = a.items.some(i => i.clinical);
        const hasClinicalB = b.items.some(i => i.clinical);

        if (hasClinicalA && !hasClinicalB) return -1;
        if (!hasClinicalA && hasClinicalB) return 1;

        // Extract patient ID from baseId (remove treatment suffix if exists)
        const aPatientId = a.baseId.split('_')[0];
        const bPatientId = b.baseId.split('_')[0];
        
        const aNum = parseInt(aPatientId) || 0;
        const bNum = parseInt(bPatientId) || 0;
        
        // 2. Sort by patient ID
        if (aNum > 0 && bNum > 0) {
            if (aNum !== bNum) {
                return aNum - bNum;
            }
        } else if (aNum === 0 && bNum === 0) {
            const strCompare = aPatientId.localeCompare(bPatientId);
            if (strCompare !== 0) {
                return strCompare;
            }
        } else {
            return aNum - bNum;
        }
        
        // 3. If same patient ID, sort by treatment type: Surgery before NAC
        if (a.groupType === 'Surgery' && b.groupType === 'NAC') {
            return -1;
        }
        if (a.groupType === 'NAC' && b.groupType === 'Surgery') {
            return 1;
        }
        return 0;
    });

    // Filter groups based on search
    const term = searchTerm.toLowerCase();
    const result = sortedGroups.filter(g => 
        g.baseId.toLowerCase().includes(term) || 
        g.items.some(i => i.id.toLowerCase().includes(term) || i.patient_id?.toLowerCase().includes(term))
    );

    return result;
  }, [patients, searchTerm]);

  const visibleGroups = groupedPatients.slice(0, displayLimit);

  const toggleGroup = useCallback((groupKey: string) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupKey)) {
        newSet.delete(groupKey);
      } else {
        newSet.add(groupKey);
      }
      return newSet;
    });
  }, []);

  // 滚动到底部自动加载更多
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
    
    // 当距离底部小于 100px 时，自动加载更多
    if (scrollBottom < 100 && !isLoadingMore.current && displayLimit < groupedPatients.length) {
      isLoadingMore.current = true;
      setDisplayLimit(prev => {
        const newLimit = prev + 50;
        setTimeout(() => {
          isLoadingMore.current = false;
        }, 500);
        return newLimit;
      });
    }
  }, [displayLimit, groupedPatients.length]);

  return (
    <div className="flex flex-col h-full w-full bg-[#0b0b0d]">
      {/* Sidebar Header */}
      <div className="h-10 shrink-0 border-b border-white/5 flex items-center justify-between px-3 bg-[#0b0b0d]">
        <span className="flex items-center gap-2 text-[11px] font-bold text-gray-300 uppercase tracking-widest">
          <Database size={12} className="text-blue-500" /> 
          {t.cohort.title}
        </span>
        <span className="text-[9px] font-mono text-gray-500 flex items-center gap-2">
          <span className={dataset === 'cropped' ? 'text-amber-500' : 'text-blue-400'}>
            {dataset === 'cropped' ? 'CROP UI' : 'ORIGINAL'}
          </span>
          <span>CASES: {groupedPatients.length}</span>
        </span>
      </div>

      {/* Search */}
      <div className="p-3 border-b border-white/5 bg-[#0b0b0d]">
        <div className="relative group">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-600 group-focus-within:text-blue-500 transition-colors" size={12} />
          <input 
            type="text" 
            placeholder={t.cohort.search} 
            className="w-full bg-[#18181b] border border-border-col text-gray-200 text-xs rounded pl-8 pr-2 py-1.5 focus:outline-none focus:border-blue-500/50 focus:bg-[#202024] transition-all placeholder:text-gray-600 font-mono"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Grouped List */}
      <div 
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto min-h-0 scrollbar-thin scrollbar-thumb-neutral-700 scrollbar-track-transparent pb-4"
        onScroll={handleScroll}
      >
        {loading ? (
          <div className="divide-y divide-white/5">
            {[...Array(5)].map((_, i) => (
              <PatientListGroupSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {visibleGroups.map(group => {
              // Create unique key for this group (patientId + treatmentType)
              const groupKey = `${group.baseId}_${group.groupType}`;
              const isExpanded = expandedGroups.has(groupKey);
              const isGroupSelected = group.items.some(i => i.id === selectedId);
              
              return (
                <div key={groupKey} className="bg-[#0b0b0d]">
                  {/* Group Header */}
                  <div 
                    onClick={() => toggleGroup(groupKey)}
                    className={`
                        flex items-center justify-between px-3 py-2 cursor-pointer select-none transition-colors
                        ${isGroupSelected ? 'bg-blue-500/5' : 'hover:bg-white/5'}
                    `}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                        {isExpanded ? <ChevronDown size={12} className="text-gray-500" /> : <ChevronRight size={12} className="text-gray-500" />}
                        <Folder size={12} className={isGroupSelected ? "text-blue-400" : "text-gray-600"} />
                        <span className={`text-[11px] font-mono truncate ${isGroupSelected ? 'text-gray-200' : 'text-gray-400'}`}>
                            {cohortYear === 'gist' ? `Patient ${group.baseId}` : group.baseId}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className={`
                            text-[8px] font-bold px-1 py-0.5 rounded-sm uppercase
                            ${group.groupType === 'NAC' ? 'text-pink-500 bg-pink-500/10' : 'text-indigo-500 bg-indigo-500/10'}
                        `}>
                            {group.groupType === 'NAC' ? 'NAC' : 'SURG'}
                        </span>
                        {group.items.some(p => p.clinical) && (
                            <span className="text-[8px] bg-blue-500/20 text-blue-400 px-1 py-0.5 rounded border border-blue-500/30" title="Has clinical data">
                                CLIN
                            </span>
                        )}
                        <span className="text-[9px] text-gray-600 bg-white/5 px-1.5 rounded-full">
                            {group.items.length}
                        </span>
                    </div>
                  </div>

                  {/* Group Items (Images) */}
                  {isExpanded && (
                    <div className="bg-[#08080a] shadow-inner">
                        {group.items.map((p, index) => {
                            const isSelected = selectedId === p.id;
                            // Use a more unique key: groupKey + index + id to ensure uniqueness
                            const uniqueKey = `${groupKey}_${index}_${p.id}`;
                            return (
                                <div 
                                    key={uniqueKey}
                                    onClick={() => onSelect(p)}
                                    className={`
                                        flex items-center gap-3 pl-8 pr-3 py-2 cursor-pointer border-l-2 transition-all
                                        ${isSelected 
                                            ? 'border-blue-500 bg-blue-500/10 text-blue-100' 
                                            : 'border-transparent text-gray-500 hover:text-gray-300 hover:bg-white/5'}
                                    `}
                                >
                                    <FileImage size={10} />
                                    <div className="flex flex-col min-w-0 flex-1">
                                        <span className="text-[10px] font-mono truncate">
                                            {p.id_short}
                                        </span>
                                        {p.clinical && (
                                            <div className="flex items-center gap-2 mt-0.5">
                                                {p.clinical.biomarkers.cea_positive && (
                                                    <span className="text-[8px] bg-red-500/20 text-red-400 px-1 rounded border border-red-500/30">CEA+</span>
                                                )}
                                                {p.clinical.biomarkers.ca199_positive && (
                                                    <span className="text-[8px] bg-red-500/20 text-red-400 px-1 rounded border border-red-500/30">CA199+</span>
                                                )}
                                                <span className="text-[8px] bg-white/10 text-gray-300 px-1 rounded border border-white/10">
                                                    F{p.frame_count}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                  )}
                </div>
              );
            })}
            
            {/* Load More Trigger - 显示剩余数量，但自动加载 */}
            {groupedPatients.length > displayLimit && (
                <div className="w-full py-3 text-center">
                    <span className="text-[9px] text-gray-600 font-mono">
                        {groupedPatients.length - displayLimit} more available (scroll to load)
                    </span>
                </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
