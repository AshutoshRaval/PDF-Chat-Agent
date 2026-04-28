"""
RAGAS evaluation — scores the RAG pipeline quality using Claude as the judge.

Metrics:
  Faithfulness       — is the answer grounded in the retrieved chunks? (no hallucination)
  Context Precision  — were the right chunks retrieved?
  Factual Correctness — does the answer match the known ground truth?

Usage:
    TEST_PDF_ID=<your-pdf-id> python tests/eval_ragas.py
"""
import os
import sys
import json
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, context_precision
from ragas.metrics import FactualCorrectness
from ragas.llms import LangchainLLMWrapper
from langchain_anthropic import ChatAnthropic

from services.chat import answer_question

TEST_PDF_ID = os.getenv("TEST_PDF_ID", "")

GOLDEN_DATASET_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")


def load_eval_questions():
    with open(GOLDEN_DATASET_PATH) as f:
        cases = json.load(f)
    # only cases with a ground_truth are useful for factual correctness
    return [(c["question"], c.get("ground_truth", "")) for c in cases]


def build_dataset() -> Dataset:
    questions, answers, contexts, ground_truths = [], [], [], []

    for question, ground_truth in load_eval_questions():
        print(f"  Running: {question}")
        result = answer_question(question, pdf_id=TEST_PDF_ID or None)
        questions.append(question)
        answers.append(result["answer"])
        contexts.append([s["text"] for s in result["sources"]])
        ground_truths.append(ground_truth)

    return Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })


def score(df, col) -> str:
    if col not in df.columns:
        return "n/a"
    val = df[col].mean()
    return f"{val:.3f}" if val == val else "n/a"


def run():
    if not TEST_PDF_ID:
        print("WARNING: TEST_PDF_ID not set — evaluating across all PDFs")

    evaluator_llm = LangchainLLMWrapper(
        ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_tokens=2048,
        )
    )

    faithfulness.llm = evaluator_llm
    context_precision.llm = evaluator_llm
    factual_correctness = FactualCorrectness(llm=evaluator_llm)

    print("\nBuilding evaluation dataset...")
    dataset = build_dataset()

    print("\nRunning RAGAS evaluation...\n")
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, context_precision, factual_correctness],
    )

    df = result.to_pandas()

    print("\n" + "=" * 52)
    print("  RAGAS Evaluation Results")
    print("=" * 52)
    fc_col = next((c for c in df.columns if c.startswith("factual_correctness")), None)

    print(f"  Faithfulness:        {score(df, 'faithfulness')}  (1.0 = no hallucination)")
    print(f"  Context Precision:   {score(df, 'context_precision')}  (1.0 = perfect retrieval)")
    print(f"  Factual Correctness: {score(df, fc_col) if fc_col else 'n/a'}  (1.0 = matches ground truth)")
    print("=" * 52)

    print("\nPer-question breakdown:")
    for _, row in df.iterrows():
        print(f"\n  Q: {row['user_input']}")
        print(f"     Faithfulness:        {row.get('faithfulness', 'n/a')}")
        print(f"     Context Precision:   {row.get('context_precision', 'n/a')}")
        print(f"     Factual Correctness: {row.get(fc_col, 'n/a') if fc_col else 'n/a'}")

    print()
    return result


if __name__ == "__main__":
    run()
