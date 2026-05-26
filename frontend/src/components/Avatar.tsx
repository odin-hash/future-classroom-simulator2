import React from 'react';

interface AvatarProps {
  style: string;  // curious-boy, shy-girl, distracted-boy, hyperactive-boy, weak-learner-girl, overconfident-boy
  emotion: 'normal' | 'confused' | 'questioning' | 'sleeping' | 'distracted' | 'talking';
  name?: string;  // Student name to resolve illustration image
}

// Map avatar_style to the student name for image lookup
const STYLE_TO_NAME: Record<string, string> = {
  'curious-boy': 'aarav',
  'shy-girl': 'ananya',
  'distracted-boy': 'vihaan',
  'hyperactive-boy': 'ishaan',
  'weak-learner-girl': 'riya',
  'overconfident-boy': 'kabir',
};

export const Avatar: React.FC<AvatarProps> = ({ style, emotion, name }) => {
  // Resolve the image filename from the avatar style or name
  const studentKey = name?.toLowerCase() || STYLE_TO_NAME[style] || 'aarav';
  const imgSrc = `/students/${studentKey}.png`;

  // Animation helper class based on student state
  let animationClass = 'avatar-breathing';
  if (emotion === 'talking') {
    animationClass = 'avatar-talking';
  } else if (emotion === 'sleeping') {
    animationClass = 'avatar-sleeping';
  } else if (emotion === 'distracted') {
    animationClass = 'avatar-distracted';
  } else if (emotion === 'confused') {
    animationClass = 'avatar-confused';
  } else if (emotion === 'questioning') {
    animationClass = 'avatar-questioning';
  } else if (studentKey === 'ananya' || style === 'shy-girl') {
    animationClass = 'avatar-shy';
  }

  return (
    <div className={`student-avatar-container ${animationClass}`}>
      <div className={`student-avatar-img-wrapper ${emotion}`}>
        <img
          src={imgSrc}
          alt={name || studentKey}
          className="student-avatar-illustration"
          loading="lazy"
          draggable={false}
        />
        {/* Emotion overlay effects */}
        {emotion === 'sleeping' && (
          <div className="avatar-overlay sleeping-overlay" />
        )}
        {emotion === 'confused' && (
          <div className="avatar-overlay confused-overlay" />
        )}
        {emotion === 'distracted' && (
          <div className="avatar-overlay distracted-overlay" />
        )}
      </div>
      {emotion === 'sleeping' && (
        <span className="zzz-animation">Zzz</span>
      )}
    </div>
  );
};
