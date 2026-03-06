import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Reflection } from '../types/game';
import { TypewriterText } from './TypewriterText';

interface ReflectionViewProps {
  reflection: Reflection;
  onContinue: () => void;
}

export const ReflectionView: React.FC<ReflectionViewProps> = ({ reflection, onContinue }) => {
  const [showContinue, setShowContinue] = useState(false);

  useEffect(() => {
    setShowContinue(false);
  }, [reflection.id]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8 relative z-10">
      <motion.div
        key={reflection.id}
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-4xl bg-game-darkPurple/80 backdrop-blur-md border border-game-pink/50 box-glow-pink p-8 md:p-12 rounded-sm"
      >
        <TypewriterText
          text={reflection.text}
          speed={30}
          className="font-dialog text-2xl md:text-3xl text-game-lightGray italic leading-relaxed"
          onComplete={() => setTimeout(() => setShowContinue(true), 1000)}
        />
        {showContinue && (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onContinue}
            className="mt-8 px-8 py-4 border border-game-pink text-game-pink font-pixel text-lg hover:bg-game-pink/20 transition-colors"
          >
            ПРОДОВЖИТИ
          </motion.button>
        )}
      </motion.div>
    </div>
  );
};
