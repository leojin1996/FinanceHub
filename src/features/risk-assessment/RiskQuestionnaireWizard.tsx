import { useState } from "react";

import { type Locale, useAppState } from "../../app/state/app-state";
import { questionnaire } from "../../mock/questionnaire";
import {
  buildAssessmentResult,
  type AnswerScore,
  type RiskAssessmentResult,
} from "./risk-scoring";

function getWizardCopy(locale: Locale, stepIndex: number) {
  const isLastStep = stepIndex === questionnaire.length - 1;

  if (locale === "en-US") {
    return {
      nextButtonLabel: isLastStep ? "Submit" : "Next",
      progressLabel: `Question ${stepIndex + 1} of ${questionnaire.length}`,
    };
  }

  return {
    nextButtonLabel: isLastStep ? "提交" : "下一题",
    progressLabel: `第 ${stepIndex + 1} / ${questionnaire.length} 题`,
  };
}

interface RiskQuestionnaireWizardProps {
  onComplete: (result: RiskAssessmentResult) => void;
}

export function RiskQuestionnaireWizard({ onComplete }: RiskQuestionnaireWizardProps) {
  const { locale } = useAppState();
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<AnswerScore[]>([]);

  const currentQuestion = questionnaire[stepIndex];
  const currentScore = answers[stepIndex]?.score ?? null;
  const wizardCopy = getWizardCopy(locale, stepIndex);

  function handleSelect(score: number) {
    setAnswers((currentAnswers) => {
      const nextAnswers = [...currentAnswers];
      nextAnswers[stepIndex] = { dimension: currentQuestion.dimension, score };
      return nextAnswers;
    });
  }

  function handleContinue() {
    if (currentScore === null) {
      return;
    }

    if (stepIndex === questionnaire.length - 1) {
      onComplete(buildAssessmentResult(answers));
      return;
    }

    setStepIndex((currentStepIndex) => currentStepIndex + 1);
  }

  return (
    <section className="panel questionnaire-panel">
      <p className="questionnaire-panel__progress">{wizardCopy.progressLabel}</p>
      <h2>{locale === "zh-CN" ? currentQuestion.promptZh : currentQuestion.promptEn}</h2>
      <div className="questionnaire-options">
        {currentQuestion.answers.map((answer) => {
          const label = locale === "zh-CN" ? answer.labelZh : answer.labelEn;

          return (
            <label className="questionnaire-option" key={`${currentQuestion.id}-${label}`}>
              <input
                checked={currentScore === answer.score}
                name={`question-${currentQuestion.id}`}
                onChange={() => handleSelect(answer.score)}
                type="radio"
              />
              <span>{label}</span>
            </label>
          );
        })}
      </div>
      <div className="questionnaire-actions">
        <button disabled={currentScore === null} onClick={handleContinue} type="button">
          {wizardCopy.nextButtonLabel}
        </button>
      </div>
    </section>
  );
}
