import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
interface TypewriterTextProps {
  text: string;
  speed?: number;
  className?: string;
  onComplete?: () => void;
}
export const TypewriterText: React.FC<TypewriterTextProps> = ({
  text,
  speed = 30,
  className = '',
  onComplete
}) => {
  const [displayedText, setDisplayedText] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [hasCompleted, setHasCompleted] = useState(false);
  useEffect(() => {
    setDisplayedText('');
    setCurrentIndex(0);
    setHasCompleted(false);
  }, [text]);
  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setDisplayedText((prev) => prev + text[currentIndex]);
        setCurrentIndex((prev) => prev + 1);
      }, speed);
      return () => clearTimeout(timeout);
    } else if (onComplete && !hasCompleted) {
      setHasCompleted(true);
      onComplete();
    }
  }, [currentIndex, text, speed, onComplete, hasCompleted]);
  return (
    <motion.div
      initial={{
        opacity: 0
      }}
      animate={{
        opacity: 1
      }}
      className={className}>

      {displayedText}
      <motion.span
        animate={{
          opacity: [1, 0]
        }}
        transition={{
          repeat: Infinity,
          duration: 0.8
        }}
        className="inline-block w-2 h-5 bg-game-cyan ml-1 align-middle" />

    </motion.div>);

};