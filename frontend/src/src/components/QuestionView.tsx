import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Question, Answer } from '../types/game';
import { TypewriterText } from './TypewriterText';

interface QuestionViewProps {
  question: Question;
  totalQuestions: number;
  onAnswer: (answer: Answer) => void;
}

export const QuestionView: React.FC<QuestionViewProps> = ({
  question,
  totalQuestions,
  onAnswer
}) => {
  const [showAnswers, setShowAnswers] = useState(false);
  const [selectedAnswerId, setSelectedAnswerId] = useState<string | null>(null);
  const [customText, setCustomText] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);

  const handleAnswerClick = (answer: Answer) => {
    setSelectedAnswerId(answer.id);
    setTimeout(() => {
      onAnswer(answer);
      setShowAnswers(false);
      setSelectedAnswerId(null);
      setCustomText('');
      setShowCustomInput(false);
    }, 700);
  };

  const handleCustomSubmit = () => {
    if (!customText.trim()) return;
    const customAnswer: Answer = {
      id: 'custom',
      text: customText.trim(),
      effects: {},
    };
    handleAnswerClick(customAnswer);
  };
  return (
    <>
      <div className="flex flex-col items-center justify-center min-h-screen p-4 md:p-8 relative z-10">
        {/* Progress Indicator */}
        <div className="absolute top-8 left-8 font-pixel text-sm text-game-cyan text-glow-cyan">
          АКТ {question.id} / {totalQuestions}
        </div>

        <motion.div
          key={question.id}
          initial={{
            opacity: 0,
            scale: 0.95,
            y: 20
          }}
          animate={{
            opacity: 1,
            scale: 1,
            y: 0
          }}
          exit={{
            opacity: 0,
            scale: 1.05,
            filter: 'blur(10px)',
            y: -20
          }}
          transition={{
            duration: 0.6,
            ease: 'easeOut'
          }}
          className="w-full max-w-4xl bg-game-darkPurple/80 backdrop-blur-md border border-game-cyan box-glow-cyan p-6 md:p-10 rounded-sm relative overflow-hidden">

          {/* Scanline effect inside dialog */}
          <div className="absolute inset-0 bg-scanlines opacity-20 pointer-events-none"></div>

          <div className="min-h-[120px] mb-8 relative z-10">
            <TypewriterText
              key={`q-${question.id}`}
              text={question.text}
              className="font-dialog text-3xl md:text-4xl text-white leading-relaxed"
              speed={20}
              onComplete={() => setShowAnswers(true)} />

          </div>

          <AnimatePresence>
            {showAnswers &&
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-4 relative z-10">

              {question.answers.map((answer, index) =>
                <motion.button
                  key={answer.id}
                  initial={{ opacity: 0, x: -30 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1, duration: 0.4, ease: 'easeOut' }}
                  whileHover={{
                    scale: 1.01,
                    x: 15,
                    backgroundColor: 'rgba(255, 45, 111, 0.15)',
                    borderColor: '#ff2d6f',
                    boxShadow: '0 0 15px rgba(255,45,111,0.3)'
                  }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleAnswerClick(answer)}
                  disabled={selectedAnswerId !== null}
                  className={`w-full text-left p-5 border border-game-lightGray/30 font-dialog text-xl md:text-2xl text-game-lightGray transition-all duration-300 group flex items-start
                    ${selectedAnswerId === answer.id ? 'bg-game-pink/30 border-game-pink text-white box-glow-pink scale-[1.02] x-4' : ''}
                    ${selectedAnswerId !== null && selectedAnswerId !== answer.id ? 'opacity-20 blur-[2px]' : ''}
                  `}>
                  <span className={`text-game-pink mr-4 font-pixel text-sm mt-1.5 transition-colors duration-300 ${selectedAnswerId === answer.id ? 'text-white text-glow-pink' : 'group-hover:text-glow-pink'}`}>
                    {'>'}
                  </span>
                  <span className={`transition-colors duration-300 ${selectedAnswerId === answer.id ? 'text-white' : 'group-hover:text-white'}`}>
                    {answer.text}
                  </span>
                </motion.button>
              )}

              {/* Custom answer option */}
              {question.allowCustom && (
                <motion.div
                  initial={{ opacity: 0, x: -30 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: question.answers.length * 0.1, duration: 0.4, ease: 'easeOut' }}
                  className="border border-game-cyan/30 transition-all duration-300">

                  {!showCustomInput ? (
                    <button
                      onClick={() => setShowCustomInput(true)}
                      disabled={selectedAnswerId !== null}
                      className="w-full text-left p-5 font-dialog text-xl md:text-2xl text-game-cyan/60 hover:text-game-cyan hover:bg-game-cyan/10 transition-all duration-300 group flex items-start">
                      <span className="text-game-cyan mr-4 font-pixel text-sm mt-1.5 group-hover:text-glow-cyan">{'>'}</span>
                      <span>своя відповідь...</span>
                    </button>
                  ) : (
                    <div className="p-5 space-y-3">
                      <textarea
                        value={customText}
                        onChange={(e) => setCustomText(e.target.value)}
                        placeholder="напиши свою відповідь"
                        rows={2}
                        autoFocus
                        className="w-full bg-transparent border border-game-cyan/40 text-white font-dialog text-lg p-3 resize-none placeholder-game-lightGray/40 focus:outline-none focus:border-game-cyan focus:box-glow-cyan"
                      />
                      <div className="flex gap-3">
                        <motion.button
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.97 }}
                          onClick={handleCustomSubmit}
                          disabled={!customText.trim() || selectedAnswerId !== null}
                          className="px-6 py-2 border border-game-cyan text-game-cyan font-pixel text-sm hover:bg-game-cyan/20 hover:text-glow-cyan disabled:opacity-30 transition-all duration-200">
                          ПІДТВЕРДИТИ
                        </motion.button>
                        <button
                          onClick={() => { setShowCustomInput(false); setCustomText(''); }}
                          className="px-4 py-2 text-game-lightGray/50 font-pixel text-sm hover:text-game-lightGray transition-colors duration-200">
                          скасувати
                        </button>
                      </div>
                    </div>
                  )}
                </motion.div>
              )}

            </motion.div>
            }
          </AnimatePresence>
        </motion.div>
      </div>
    </>);

};