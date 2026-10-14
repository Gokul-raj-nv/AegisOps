interface ConfidenceMeterProps {
  confidence: number; // 0.0 – 1.0
}

export default function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  const pct = Math.round(confidence * 100);
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const filled = circumference * confidence;
  const empty = circumference - filled;

  const colorClass =
    confidence >= 0.75 ? 'confidence-high' :
    confidence >= 0.5  ? 'confidence-med'  : 'confidence-low';

  const strokeColor =
    confidence >= 0.75 ? '#22c55e' :
    confidence >= 0.5  ? '#f59e0b' : '#ef4444';

  const label =
    confidence >= 0.75 ? 'High Confidence' :
    confidence >= 0.5  ? 'Medium Confidence' : 'Low Confidence';

  return (
    <div className="confidence-meter">
      <div className="confidence-ring-container">
        <svg width="160" height="160" viewBox="0 0 160 160">
          <circle
            className="confidence-ring-bg"
            cx="80" cy="80" r={radius}
            strokeWidth="10"
          />
          <circle
            className="confidence-ring-fill"
            cx="80" cy="80" r={radius}
            strokeWidth="10"
            stroke={strokeColor}
            strokeDasharray={`${filled} ${empty}`}
            strokeDashoffset={circumference * 0.25}
            transform="rotate(-90 80 80)"
            style={{ filter: `drop-shadow(0 0 8px ${strokeColor}60)` }}
          />
        </svg>
        <div className="confidence-ring-text">
          <span className={`confidence-pct ${colorClass}`}>{pct}%</span>
          <span className="confidence-label">Confidence</span>
        </div>
      </div>
      <p style={{ fontSize: '0.875rem', fontWeight: 600, color: strokeColor }}>{label}</p>
      {confidence < 0.75 && (
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          Below auto-action threshold — human review required
        </p>
      )}
    </div>
  );
}
