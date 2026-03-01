import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { TypewriterText } from './TypewriterText';
interface IntroViewProps {
  onStart: () => void;
}
export const IntroView: React.FC<IntroViewProps> = ({ onStart }) => {
  const [step, setStep] = useState(0);
  return (
    <motion.div
      initial={{
        opacity: 0
      }}
      animate={{
        opacity: 1
      }}
      exit={{
        opacity: 0,
        filter: 'blur(10px)',
        scale: 1.1
      }}
      transition={{
        duration: 1.5
      }}
      className="flex flex-col items-center justify-center min-h-screen p-8 text-center bg-game-black relative z-10">

      <div className="max-w-3xl w-full space-y-12">
        <div className="min-h-[120px]">
          {step >= 0 &&
          <TypewriterText
            text="Чорний конверт. Неонова печатка. Запрошення на звану вечерю Короля Рейву."
            className="font-dialog text-2xl md:text-3xl text-game-lightGray leading-relaxed"
            speed={20}
            onComplete={() => setTimeout(() => setStep(1), 800)} />

          }
        </div>

        <div className="min-h-[100px]">
          {step >= 1 &&
          <TypewriterText
            text="Тут немає хороших чи поганих рішень. Є лише наслідки."
            className="font-dialog text-3xl md:text-4xl text-white text-glow-cyan leading-relaxed"
            speed={25}
            onComplete={() => setTimeout(() => setStep(2), 600)} />

          }
        </div>

        {step >= 2 &&
        <motion.button
          initial={{
            opacity: 0,
            y: 20
          }}
          animate={{
            opacity: 1,
            y: 0
          }}
          whileHover={{
            scale: 1.05,
            textShadow: '0 0 15px rgb(255,45,111)',
            boxShadow:
            '0 0 25px rgba(255,45,111,0.6), inset 0 0 15px rgba(255,45,111,0.3)'
          }}
          whileTap={{
            scale: 0.95
          }}
          onClick={onStart}
          className="mt-12 px-10 py-5 font-pixel text-xl text-game-pink border-2 border-game-pink box-glow-pink bg-game-black/50 backdrop-blur-sm uppercase tracking-widest transition-all duration-300 hover:bg-game-pink/10">

            [ УВІЙТИ ]
          </motion.button>
        }
      </div>
    </motion.div>);

};