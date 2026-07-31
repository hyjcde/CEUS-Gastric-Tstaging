import React from 'react';

interface RadarChartProps {
  data: number[]; // [c1, c2, c3, c4] values 0-100
  labels: string[];
  color?: string;
}

export const RadarChart: React.FC<RadarChartProps> = React.memo(({ data, labels, color = '#3b82f6' }) => {
  const size = 180;
  const center = size / 2;
  const radius = 60;
  const angleStep = (Math.PI * 2) / 4;

  // Calculate points
  const getPoint = (value: number, index: number) => {
    const angle = index * angleStep - Math.PI / 2; // Start from top
    const r = (value / 100) * radius;
    const x = center + r * Math.cos(angle);
    const y = center + r * Math.sin(angle);
    return `${x},${y}`;
  };

  const polyPoints = data.map((v, i) => getPoint(v, i)).join(' ');
  
  // Background Grid
  const levels = [25, 50, 75, 100];

  return (
    <div className="flex justify-center items-center py-4 relative select-none">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
        {/* Grid Circles */}
        {levels.map((l) => (
          <circle
            key={l}
            cx={center}
            cy={center}
            r={(l / 100) * radius}
            fill="none"
            stroke="#333"
            strokeWidth="1"
            strokeDasharray="2 2"
          />
        ))}
        
        {/* Axes */}
        {[0, 1, 2, 3].map((i) => {
            const p = getPoint(100, i).split(',');
            return <line key={i} x1={center} y1={center} x2={p[0]} y2={p[1]} stroke="#333" strokeWidth="1" />
        })}

        {/* Data Polygon */}
        <polygon
          points={polyPoints}
          fill={color}
          fillOpacity="0.2"
          stroke={color}
          strokeWidth="2"
          className="drop-shadow-[0_0_10px_currentColor] transition-all duration-500 ease-out"
        />
        
        {/* Data Points */}
        {data.map((v, i) => {
           const [x, y] = getPoint(v, i).split(',');
           return <circle key={i} cx={x} cy={y} r="3" fill="#000" stroke={color} strokeWidth="2" className="transition-all duration-500" />
        })}

        {/* Labels */}
        <text x={center} y={center - radius - 12} textAnchor="middle" fill="#888" fontSize="9" fontFamily="monospace" fontWeight="bold">{labels[0]}</text>
        <text x={center + radius + 8} y={center} textAnchor="start" fill="#888" fontSize="9" fontFamily="monospace" fontWeight="bold">{labels[1]}</text>
        <text x={center} y={center + radius + 12} textAnchor="middle" fill="#888" fontSize="9" fontFamily="monospace" fontWeight="bold">{labels[2]}</text>
        <text x={center - radius - 8} y={center} textAnchor="end" fill="#888" fontSize="9" fontFamily="monospace" fontWeight="bold">{labels[3]}</text>
      </svg>
    </div>
  );
});

RadarChart.displayName = 'RadarChart';

