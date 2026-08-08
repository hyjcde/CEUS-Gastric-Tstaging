'use client';

import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, Maximize, ChevronLeft, ChevronRight, Droplets } from 'lucide-react';
import { VideoInfo } from '@/types';
import type { Language } from '@/lib/i18n';

interface VideoPlayerProps {
  videos: VideoInfo[];
  onClose?: () => void;
  language?: Language;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({ videos, onClose, language = 'zh' }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentVideoIndex, setCurrentVideoIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(true);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [playError, setPlayError] = useState<string | null>(null);

  const currentVideo = videos[currentVideoIndex];

  // 格式化时间
  const formatTime = (time: number) => {
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  // 播放/暂停
  const togglePlay = useCallback(async () => {
    const video = videoRef.current;
    if (!video) return;
    try {
      if (video.paused) {
        setPlayError(null);
        await video.play();
        setIsPlaying(true);
      } else {
        video.pause();
        setIsPlaying(false);
      }
    } catch (error) {
      setIsPlaying(false);
      setPlayError(error instanceof Error ? error.message : '视频播放失败');
    }
  }, []);

  // 切换视频
  const switchVideo = (index: number) => {
    if (index >= 0 && index < videos.length) {
      setCurrentVideoIndex(index);
      setIsPlaying(false);
      setCurrentTime(0);
      setPlayError(null);
      setIsLoading(true);
    }
  };

  // 逐帧前进/后退
  const stepFrame = (direction: 'forward' | 'backward') => {
    if (videoRef.current) {
      const frameTime = 1 / 30; // 假设 30fps
      if (direction === 'forward') {
        videoRef.current.currentTime += frameTime;
      } else {
        videoRef.current.currentTime -= frameTime;
      }
    }
  };

  // 进度条拖动
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  // 全屏
  const toggleFullscreen = () => {
    if (videoRef.current) {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        videoRef.current.requestFullscreen();
      }
    }
  };

  // 播放速度
  const cyclePlaybackRate = () => {
    const rates = [0.25, 0.5, 1, 1.5, 2];
    const currentIndex = rates.indexOf(playbackRate);
    const nextIndex = (currentIndex + 1) % rates.length;
    const newRate = rates[nextIndex];
    setPlaybackRate(newRate);
    if (videoRef.current) {
      videoRef.current.playbackRate = newRate;
    }
  };

  // 视频事件监听
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => setCurrentTime(video.currentTime);
    const handleLoadedMetadata = () => {
      setDuration(video.duration);
      setIsLoading(false);
    };
    const handleEnded = () => setIsPlaying(false);
    const handleWaiting = () => setIsLoading(true);
    const handleCanPlay = () => setIsLoading(false);

    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('ended', handleEnded);
    video.addEventListener('waiting', handleWaiting);
    video.addEventListener('canplay', handleCanPlay);

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('ended', handleEnded);
      video.removeEventListener('waiting', handleWaiting);
      video.removeEventListener('canplay', handleCanPlay);
    };
  }, [currentVideoIndex]);

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case ' ':
          e.preventDefault();
          togglePlay();
          break;
        case 'ArrowLeft':
          if (e.shiftKey) {
            stepFrame('backward');
          } else if (videoRef.current) {
            videoRef.current.currentTime -= 5;
          }
          break;
        case 'ArrowRight':
          if (e.shiftKey) {
            stepFrame('forward');
          } else if (videoRef.current) {
            videoRef.current.currentTime += 5;
          }
          break;
        case 'ArrowUp':
          if (currentVideoIndex > 0) {
            switchVideo(currentVideoIndex - 1);
          }
          break;
        case 'ArrowDown':
          if (currentVideoIndex < videos.length - 1) {
            switchVideo(currentVideoIndex + 1);
          }
          break;
        case 'm':
          setIsMuted(!isMuted);
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [togglePlay, isMuted, currentVideoIndex, videos.length]);

  if (videos.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-black/90 text-gray-400">
        <div className="text-center">
          <div className="text-4xl mb-4">🎬</div>
          <p>{language !== 'en' ? '该患者暂无视频数据' : 'No video data for this patient'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-black">
      {/* 视频区域 */}
      <div className="flex-1 relative flex items-center justify-center bg-black min-h-0">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
            <div className="w-10 h-10 border-2 border-white/20 border-t-white rounded-full animate-spin" />
          </div>
        )}
        
        <video
          key={currentVideo.url}
          ref={videoRef}
          src={currentVideo.url}
          className="max-h-full max-w-full object-contain"
          muted={isMuted}
          controls={currentVideo.treatment === 'reader_study'}
          preload="auto"
          onClick={currentVideo.treatment === 'reader_study' ? undefined : () => { void togglePlay(); }}
          onLoadedData={() => { setIsLoading(false); setPlayError(null); }}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onError={() => { setIsLoading(false); setPlayError('视频媒体加载失败'); }}
          playsInline
        />

        {playError ? (
          <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2 rounded border border-red-400/40 bg-black/80 px-3 py-2 text-[10px] text-red-200">
            {playError}
          </div>
        ) : null}

        {/* 视频信息标签 */}
        <div className="absolute top-3 left-3 flex items-center gap-2">
          <span className="text-[10px] font-bold text-white bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-white/20">
            {currentVideo.filename}
          </span>
          {currentVideo.water_filled && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-cyan-400 bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-cyan-500/30">
              <Droplets size={10} />
              {language !== 'en' ? '喝水' : 'Water'}
            </span>
          )}
          <span className={`text-[10px] font-bold px-2 py-1 rounded border backdrop-blur-sm ${
            currentVideo.treatment === 'reader_study'
              ? 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30'
              : currentVideo.treatment === 'direct_surgery'
                ? 'text-green-400 bg-green-500/10 border-green-500/30'
                : 'text-amber-400 bg-amber-500/10 border-amber-500/30'
          }`}>
            {currentVideo.treatment === 'reader_study'
              ? (language !== 'en' ? '第一轮基线' : 'Round 1 Baseline')
              : currentVideo.treatment === 'direct_surgery'
                ? (language !== 'en' ? '直接手术' : 'Direct Surgery')
                : (language !== 'en' ? '新辅助' : 'Neoadjuvant')
            }
          </span>
        </div>

        {/* 播放/暂停大按钮；第一轮基线队列使用原生控件，避免覆盖浏览器播放手势 */}
        {currentVideo.treatment !== 'reader_study' && !isPlaying && !isLoading && (
          <button
            onClick={() => { void togglePlay(); }}
            className="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/30 transition-colors group"
          >
            <div className="w-16 h-16 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center group-hover:bg-white/30 transition-colors">
              <Play size={32} className="text-white ml-1" />
            </div>
          </button>
        )}
      </div>

      {/* 视频列表（多个视频时显示） */}
      {videos.length > 1 && (
        <div className="bg-zinc-900/80 border-t border-white/10 px-3 py-2">
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin">
            <span className="text-[10px] text-gray-500 font-medium shrink-0">
              {language !== 'en' ? '视频' : 'Videos'} ({videos.length})
            </span>
            {videos.map((video, idx) => (
              <button
                key={video.url}
                onClick={() => switchVideo(idx)}
                className={`shrink-0 px-2.5 py-1 rounded text-[10px] font-medium transition-all ${
                  idx === currentVideoIndex
                    ? 'bg-white text-black'
                    : 'bg-white/10 text-gray-400 hover:bg-white/20 hover:text-white'
                }`}
              >
                {video.filename.replace('.mp4', '')}
                {video.water_filled && ' 💧'}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 控制栏 */}
      <div className="bg-zinc-900/90 backdrop-blur-sm border-t border-white/10 px-4 py-3">
        {/* 进度条 */}
        <div className="flex items-center gap-3 mb-3">
          <span className="text-[10px] font-mono text-gray-400 w-12">
            {formatTime(currentTime)}
          </span>
          <div className="flex-1 relative h-1 bg-white/10 rounded-full overflow-hidden">
            <div 
              className="absolute inset-y-0 left-0 bg-white/80 rounded-full"
              style={{ width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%` }}
            />
            <input
              type="range"
              min={0}
              max={duration || 100}
              value={currentTime}
              onChange={handleSeek}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
          </div>
          <span className="text-[10px] font-mono text-gray-400 w-12 text-right">
            {formatTime(duration)}
          </span>
        </div>

        {/* 控制按钮 */}
        <div className="flex items-center justify-between">
          {/* 左侧：视频切换 */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => switchVideo(currentVideoIndex - 1)}
              disabled={currentVideoIndex === 0}
              className="p-2 rounded-lg hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={16} className="text-gray-400" />
            </button>
            <span className="text-[10px] text-gray-500 font-mono px-2">
              {currentVideoIndex + 1} / {videos.length}
            </span>
            <button
              onClick={() => switchVideo(currentVideoIndex + 1)}
              disabled={currentVideoIndex === videos.length - 1}
              className="p-2 rounded-lg hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={16} className="text-gray-400" />
            </button>
          </div>

          {/* 中间：播放控制 */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => stepFrame('backward')}
              className="p-2 rounded-lg hover:bg-white/10 transition-colors"
              title={language !== 'en' ? '后退一帧 (Shift+←)' : 'Step backward (Shift+←)'}
            >
              <SkipBack size={14} className="text-gray-400" />
            </button>
            <button
              onClick={togglePlay}
              className="p-3 rounded-full bg-white/10 hover:bg-white/20 transition-colors mx-2"
            >
              {isPlaying ? (
                <Pause size={20} className="text-white" />
              ) : (
                <Play size={20} className="text-white ml-0.5" />
              )}
            </button>
            <button
              onClick={() => stepFrame('forward')}
              className="p-2 rounded-lg hover:bg-white/10 transition-colors"
              title={language !== 'en' ? '前进一帧 (Shift+→)' : 'Step forward (Shift+→)'}
            >
              <SkipForward size={14} className="text-gray-400" />
            </button>
          </div>

          {/* 右侧：其他控制 */}
          <div className="flex items-center gap-1">
            <button
              onClick={cyclePlaybackRate}
              className="px-2 py-1 rounded-lg hover:bg-white/10 transition-colors text-[10px] font-mono text-gray-400"
              title={language !== 'en' ? '播放速度' : 'Playback speed'}
            >
              {playbackRate}x
            </button>
            <button
              onClick={() => setIsMuted(!isMuted)}
              className="p-2 rounded-lg hover:bg-white/10 transition-colors"
              title={language !== 'en' ? '静音 (M)' : 'Mute (M)'}
            >
              {isMuted ? (
                <VolumeX size={14} className="text-gray-400" />
              ) : (
                <Volume2 size={14} className="text-gray-400" />
              )}
            </button>
            <button
              onClick={toggleFullscreen}
              className="p-2 rounded-lg hover:bg-white/10 transition-colors"
              title={language !== 'en' ? '全屏' : 'Fullscreen'}
            >
              <Maximize size={14} className="text-gray-400" />
            </button>
          </div>
        </div>

        {/* 快捷键提示 */}
        <div className="mt-2 text-center">
          <span className="text-[9px] text-gray-600">
            {language !== 'en' 
              ? '空格: 播放/暂停 | ←→: 快进/快退 | Shift+←→: 逐帧 | ↑↓: 切换视频'
              : 'Space: Play/Pause | ←→: Seek | Shift+←→: Frame | ↑↓: Switch video'
            }
          </span>
        </div>
      </div>
    </div>
  );
};

export default VideoPlayer;

