"use client";

import React, { useEffect, useState } from 'react';
import { Header } from '@/components/Header';
import { User, Mail, Phone, MapPin, Award, BookOpen, Calendar, Activity } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';

export default function ProfilePage() {
  const { t, dataset, language } = useSettings();
  const [stats, setStats] = useState({ totalCases: 0 });

  useEffect(() => {
    fetch(`/api/patients?dataset=${dataset}`)
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
           setStats(s => ({ ...s, totalCases: data.length }));
        }
      })
      .catch(console.error);
  }, [dataset]);

  return (
    <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200 overflow-hidden">
      <div className="h-16 shrink-0 border-b border-white/10 z-50">
        <Header />
      </div>

      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <div className="max-w-5xl mx-auto space-y-6">
          
          {/* Profile Header */}
          <div className="bg-gradient-to-br from-neutral-900/80 to-neutral-800/40 border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
            <div className="bg-gradient-to-r from-blue-600/20 to-blue-500/20 h-24"></div>
            <div className="px-8 pb-8 -mt-12">
              <div className="flex items-start gap-6">
                <div className="w-28 h-28 rounded-2xl bg-gradient-to-tr from-blue-600 to-blue-500 flex items-center justify-center text-3xl font-bold text-white shadow-2xl border-4 border-neutral-900">
                  DR
                </div>
                <div className="flex-1 pt-2">
                  <h1 className="text-3xl font-bold text-white mb-2">{t.userMenu.name}</h1>
                  <p className="text-blue-400 font-semibold text-lg mb-6">{t.userMenu.role}</p>
                  
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div className="flex items-center gap-3 p-3 bg-white/5 rounded-lg border border-white/10">
                      <Mail size={16} className="text-blue-400" />
                      <span className="text-gray-300">dr.lin@fujian-xiehe.cn</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white/5 rounded-lg border border-white/10">
                      <Phone size={16} className="text-blue-400" />
                      <span className="text-gray-300">+86 591 8888 8888</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white/5 rounded-lg border border-white/10">
                      <MapPin size={16} className="text-blue-400" />
                      <span className="text-gray-300">{t.hospital}, {t.dept}</span>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white/5 rounded-lg border border-white/10">
                      <Calendar size={16} className="text-blue-400" />
                      <span className="text-gray-300">{language === 'zh' ? '入职日期' : 'Joined'}: 2018-03-15</span>
                </div>
                </div>
                </div>
              </div>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/10 border border-blue-500/30 p-6 rounded-xl shadow-lg hover:shadow-xl transition-all">
               <div className="flex items-center gap-3 mb-3 text-gray-400 text-xs font-bold uppercase tracking-wider">
                 <BookOpen size={16} className="text-blue-400" /> 
                 {language === 'zh' ? '总病例数' : 'Total Cases'}
               </div>
               <div className="text-4xl font-mono font-bold text-white mb-1">{stats.totalCases}</div>
               <div className="text-xs text-gray-500">{language === 'zh' ? '累计诊断' : 'Cumulative'}</div>
            </div>
            <div className="bg-gradient-to-br from-amber-900/30 to-amber-800/10 border border-amber-500/30 p-6 rounded-xl shadow-lg hover:shadow-xl transition-all">
               <div className="flex items-center gap-3 mb-3 text-gray-400 text-xs font-bold uppercase tracking-wider">
                 <Award size={16} className="text-amber-400" /> 
                 {language === 'zh' ? '准确率' : 'Accuracy'}
               </div>
               <div className="text-4xl font-mono font-bold text-white mb-1">94.2%</div>
               <div className="text-xs text-gray-500">{language === 'zh' ? '模型性能' : 'Model Performance'}</div>
            </div>
            <div className="bg-gradient-to-br from-emerald-900/30 to-emerald-800/10 border border-emerald-500/30 p-6 rounded-xl shadow-lg hover:shadow-xl transition-all">
               <div className="flex items-center gap-3 mb-3 text-gray-400 text-xs font-bold uppercase tracking-wider">
                 <Activity size={16} className="text-emerald-400" /> 
                 {language === 'zh' ? '平均用时' : 'Avg. Time'}
               </div>
               <div className="text-4xl font-mono font-bold text-white mb-1">4.5m</div>
               <div className="text-xs text-gray-500">{language === 'zh' ? '每例诊断' : 'Per Case'}</div>
            </div>
          </div>

          {/* Recent Activity */}
          <div className="bg-gradient-to-br from-neutral-900/80 to-neutral-800/40 border border-white/10 rounded-xl overflow-hidden shadow-xl">
            <div className="px-6 py-4 border-b border-white/10 bg-gradient-to-r from-neutral-900 to-neutral-800">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-blue-400" />
                <span className="font-bold text-sm text-gray-200">{language === 'zh' ? '最近活动记录' : 'Recent Activity Log'}</span>
              </div>
            </div>
            <div className="divide-y divide-white/5">
              {[1,2,3,4,5,6,7,8].map((i) => (
                <div key={i} className="px-6 py-3 flex justify-between items-center hover:bg-white/5 transition-colors group">
                   <div className="flex items-center gap-3">
                      <div className="w-2 h-2 rounded-full bg-blue-500 group-hover:bg-blue-400 transition-colors"></div>
                      <span className="text-sm text-gray-300 font-mono">{language === 'zh' ? '病例审查' : 'Case review'}: 1MC_142471{i}</span>
                   </div>
                   <span className="text-xs text-gray-600 font-mono group-hover:text-gray-500 transition-colors">2023-11-19 14:3{i}</span>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}

