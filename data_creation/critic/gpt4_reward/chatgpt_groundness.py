import openai
import pandas as pd
import argparse
import json
from collections import Counter
from tqdm import tqdm
import backoff
from openai.error import APIError, Timeout, APIConnectionError
import jsonlines
import random

openai.api_key_path = "your_path_to_use_chatgpt_api"
@backoff.on_exception(backoff.expo, openai.error.RateLimitError)
def completions_with_backoff(**kwargs):
    return openai.ChatCompletion.create(**kwargs)

KNOWLEDGE_INSTRUCTIONS = {"nq": "Please answer the following questions using the shortest possible response. For example, if the question asks 'What is the capital of France?'', you can simply reply with 'Paris'.",
                          "fever": "Determine whether the following statement is true or false.",
                          "wow": "You have been provided with a chat history between two agents, separated by new lines. Generate a response that is informative and engaging based on the latest message."}

PROMPT_DICT = {
    "context": (
        "You will receive an instruction, evidence, and output.\n"
        "Your task is to evaluate if the output is fully supported by the information provided in the evidence.\n"
        "Use the following entailment scale to generate a score:\n"
        "5: Fully supported - All information in output is supported by the evidence, or extractions from the evidence. This is a somewhat extreme case and is only applicable when the output and part of the evidence are almost identical.\n"
        "4: Mostly supported - Most of the information in the output is supported by the evidence, but there is some minor information that is not supported. In other words, if an output is a paraphrase of the evidence or a less concrete version of the descriptions of the evidence, it should be considered a 4.\n"
        "3: Partially supported - The output is supported by the evidence to some extent, but there is major information in the output that is not discussed in the evidence. For example, if an instruction asks about two concepts and the evidence only discusses either of them, it should be considered a 3. If the output covers a lot of new information that is not discussed in the evidence, it should be 3.\n"
        "2: Little support - The output and evidence are only loosely related, and most of the information in the output isn't supported by the evidence.\n"
        "1: Ignore / Contradictory - The output completely ignores evidence or contradicts the evidence. This can also happen if the evidence is irrelevant to the instruction.\n"
        "Make sure to not use any external information/knowledge to judge whether the output is true or not.\n"
        "Only check whether the output is supported by the evidence, and not whether the output follows the instructions or not.\n\n"
        "###\nInstruction: Explain the use of word embeddings in Natural Language Processing\n\n"
        "Output: Word embeddings are one of the most powerful tools available for Natural Language Processing (NLP). They are mathematical representations of words or phrases in a vector space, allowing similarities between words and the context in which they are used to be measured. Word embeddings are useful for tasks such as sentiment analysis, text classification, predicting the next word in a sequence, and understanding synonyms and analogies. They allow for words to be processed as numerical values, giving machines an easier way to perform NLP tasks.\n\n"
        "Evidence: Word embedding\nWord embedding is the collective name for a set of language modeling and feature learning techniques in natural language processing (NLP) where words or phrases from the vocabulary are mapped to vectors of real numbers. Conceptually it involves a mathematical embedding from a space with one dimension per word to a continuous vector space with a much lower dimension. Methods to generate this mapping include neural networks, dimensionality reduction on the word co-occurrence matrix, probabilistic models, explainable knowledge base method, and explicit representation in terms of the context in which words appear. Word and phrase embeddings, when used as the underlying input representation, have been shown to boost the performance in NLP tasks such as syntactic parsing and sentiment analysis.\n\n"
        "Score: 4\n"
        "Explanation: Although the wording isn't exactly same, the evidence verifies all of the claims in the output such as definitions and the use cases in NLP. Therefore, it should be rated as 4.\n\n"
        "###\nInstruction: {instruction}\n\n"
        "Output: {output}\n\n"
        "Evidence: {evidence}\n\n"
        "Score:"
    ),
    "multi": (
        "You will receive an instruction, evidence, and output, and optional preceding sentences.  If the preceding sentence is given, the output should be the sentence that follows those preceding sentences. Your task is to evaluate if the output is fully supported by the information provided in the evidence, and provide explanations on your judgement\n"
        "Use the following entailment scale to generate a score:\n"
        "[Fully supported] - All information in output is supported by the evidence, or extractions from the evidence. This is only applicable when the output and part of the evidence are almost identical.\n"
        "[Partially supported] - The output is supported by the evidence to some extent, but there is major information in the output that is not discussed in the evidence. For example, if an instruction asks about two concepts and the evidence only discusses either of them, it should be considered a [Partially supported].\n"
        "[No support / Contradictory] - The output completely ignores evidence, is unrelated to the evidence, or contradicts the evidence. This can also happen if the evidence is irrelevant to the instruction.\n\n"
        "Make sure to not use any external information/knowledge to judge whether the output is true or not. Only check whether the output is supported by the evidence, and not whether the output follows the instructions or not.\n\n"
        "###\nInstruction: Explain the use of word embeddings in Natural Language Processing.\n"
        "Preceding sentences: Word embeddings are one of the most powerful tools available for Natural Language Processing (NLP). They are mathematical representations of words or phrases in a vector space, allowing similarities between words and the context in which they are used to be measured.\n"
        "Output: Word embeddings are useful for tasks such as sentiment analysis, text classification, predicting the next word in a sequence, and understanding synonyms and analogies.\n"
        "Evidence: Word embedding\nWord embedding is the collective name for a set of language modeling and feature learning techniques in natural language processing (NLP) where words or phrases from the vocabulary are mapped to vectors of real numbers. Word and phrase embeddings, when used as the underlying input representation, have been shown to boost the performance in NLP tasks such as syntactic parsing, sentiment analysis, next token predictions as well as analogy detection.\n"
        "Score: [Fully supported]\n"
        "Explanation: The output sentence discusses the application of word embeddings, and the evidence mentions all of the applications syntactic parsing, sentiment analysis, next token predictions as well as analogy detection as the applications. Therefore, the score should be [Fully supported].\n\n"
        "###\n"
        "Instruction: {instruction}\n"
        "Preceding sentences: {preceding_sentences}\n"
        "Output: {target_output}\n"
        "Evidence: {evidence}\n"
        "Score: "
    ),
    "multi_no_preceding": (
        "You will receive an instruction, evidence, and output, and optional preceding sentences.  If the preceding sentence is given, the output should be the sentence that follows those preceding sentences. Your task is to evaluate if the output is fully supported by the information provided in the evidence, and provide explanations on your judgement.\n"
        "Use the following entailment scale to generate a score:\n"
        "[Fully supported] - All information in output is supported by the evidence, or extractions from the evidence. This is only applicable when the output and part of the evidence are almost identical.\n"
        "[Partially supported] - The output is supported by the evidence to some extent, but there is major information in the output that is not discussed in the evidence. For example, if an instruction asks about two concepts and the evidence only discusses either of them, it should be considered a [Partially supported].\n"
        "[No support / Contradictory] - The output completely ignores evidence, is unrelated to the evidence, or contradicts the evidence. This can also happen if the evidence is irrelevant to the instruction.\n\n"
        "Make sure to not use any external information/knowledge to judge whether the output is true or not. Only check whether the output is supported by the evidence, and not whether the output follows the instructions or not.\n\n"
        "###\nInstruction: Explain the use of word embeddings in Natural Language Processing.\n"
        "Preceding sentences: Word embeddings are one of the most powerful tools available for Natural Language Processing (NLP). They are mathematical representations of words or phrases in a vector space, allowing similarities between words and the context in which they are used to be measured.\n"
        "Output: Word embeddings are useful for tasks such as sentiment analysis, text classification, predicting the next word in a sequence, and understanding synonyms and analogies.\n"
        "Evidence: Word embedding\nWord embedding is the collective name for a set of language modeling and feature learning techniques in natural language processing (NLP) where words or phrases from the vocabulary are mapped to vectors of real numbers. Word and phrase embeddings, when used as the underlying input representation, have been shown to boost the performance in NLP tasks such as syntactic parsing, sentiment analysis, next token predictions as well as analogy detection.\n"
        "Score: [Fully supported]\n"
        "Explanation: The output sentence discusses the application of word embeddings, and the evidence mentions all of the applications syntactic parsing, sentiment analysis, next token predictions as well as analogy detection as the applications. Therefore, the score should be [Fully supported].\n\n"
        "###\n"
        "Instruction: {instruction}\n"
        "Output: {target_output}\n"
        "Evidence: {evidence}\n"
        "Score: "
    ),
    "bio_multi_no_preceding": (
        "You will receive an instruction, evidence, and output, and optional preceding sentences.  If the preceding sentence is given, the output should be the sentence that follows those preceding sentences. Your task is to evaluate if the output is fully supported by the information provided in the evidence, and provide explanations on your judgement.\n"
        "Use the following entailment scale to generate a score:\n"
        "[Fully supported] - All information in output is supported by the evidence, or extractions from the evidence. This is only applicable when the output and part of the evidence are almost identical.\n"
        "[Partially supported] - The output is supported by the evidence to some extent, but there is major information in the output that is not discussed in the evidence. For example, if an instruction asks about two concepts and the evidence only discusses either of them, it should be considered a [Partially supported].\n"
        "[No support / Contradictory] - The output completely ignores evidence, is unrelated to the evidence, or contradicts the evidence. This can also happen if the evidence is irrelevant to the instruction.\n\n"
        "Make sure to not use any external information/knowledge to judge whether the output is true or not. Only check whether the output is supported by the evidence, and not whether the output follows the instructions or not.\n\n"
        "###\nInstruction: Ask about your symptoms and potential cardiovascular-related issues.\nI've been feeling intense discomfort in my chest during physical exertion. It sometimes shoots up to my left shoulder. There's also some mild shortness of breath.\n"
        "Output: Based on the symptoms you have described, it is important to consider potential cardiovascular-related issues. Chest discomfort during physical exertion, shooting pain to the left shoulder, and mild shortness of breath can be indicative of a heart problem.These symptoms could potentially be related to angina, which is chest pain or discomfort caused by reduced blood flow to the heart. It commonly occurs during exercise or periods of stress. Another possibility is a myocardial infarction (heart attack), where there is a blockage in one of the coronary arteries supplying blood to the heart muscle.Given the seriousness of these symptoms, I would strongly advise you to seek immediate medical attention and consult with a healthcare professional for a proper evaluation and diagnosis. They will be able to conduct a thorough examination, ask additional questions about your medical history, possibly order tests such as an electrocardiogram (ECG) or stress test, and provide appropriate treatment recommendations based on their findings.\n"
        "Evidence: Disparities in Awareness of Myocardial Infarction and Stroke Symptoms and Response Among United States– and Foreign‐Born Adults in the National Health Interview Survey. Knowledge of MI symptoms was assessed based on responses to the question, “Which of the following would you say are the symptoms that someone may be having a heart attack?” Responses were pain or discomfort in the jaw, neck, or back; feeling weak, lightheaded, or faint; chest pain or discomfort; pain or discomfort in the arms or shoulder; and shortness of breath. Similarly, knowledge of stroke symptoms was assessed by an individual’s response to the question, “Which of the following would you say are the symptoms that someone may be having a stroke?” Responses were sudden numbness or weakness of face, arm, or leg, especially on one side; sudden confusion or trouble speaking; sudden trouble seeing in one or both eyes; sudden trouble walking, dizziness, or loss of balance; and sudden severe headache with no known cause. Respondents who answered “yes” to the 5 queries on MI and stroke symptoms were classified as knowing the symptoms of MI and stroke. Those who answered “no,” “don’t know,” or refused to answer were classified as not knowing the symptoms.\n"
        "Score: [Fully supported]\n"
        "Explanation:The output correctly identifies potential cardiovascular-related issues including angina and myocardial infarction (heart attack) based on the described symptoms. The evidence supports these concerns, mentioning commonly recognized symptoms of a heart attack including chest pain or discomfort, shooting pain in the shoulder, and shortness of breath. The output also correctly advises seeking immediate medical attention and consultation with a healthcare professional, which is an appropriate advice given the severity of these conditions.\n\n"
        "###\n"
        "Instruction: {instruction}\n"
        "Output: {target_output}\n"
        "Evidence: {evidence}\n"
        "Score: "
    ),
    "bio_multi": (
        "You will receive an instruction, evidence, and output, and optional preceding sentences.  If the preceding sentence is given, the output should be the sentence that follows those preceding sentences. Your task is to evaluate if the output is fully supported by the information provided in the evidence, and provide explanations on your judgement\n"
        "Use the following entailment scale to generate a score:\n"
        "[Fully supported] - All information in output is supported by the evidence, or extractions from the evidence. This is only applicable when the output and part of the evidence are almost identical.\n"
        "[Partially supported] - The output is supported by the evidence to some extent, but there is major information in the output that is not discussed in the evidence. For example, if an instruction asks about two concepts and the evidence only discusses either of them, it should be considered a [Partially supported].\n"
        "[No support / Contradictory] - The output completely ignores evidence, is unrelated to the evidence, or contradicts the evidence. This can also happen if the evidence is irrelevant to the instruction.\n\n"
        "Make sure to not use any external information/knowledge to judge whether the output is true or not. Only check whether the output is supported by the evidence, and not whether the output follows the instructions or not.\n\n"
        "###\nInstruction: Ask about your symptoms and potential cardiovascular-related issues.\nI've been feeling intense discomfort in my chest during physical exertion. It sometimes shoots up to my left shoulder. There's also some mild shortness of breath.\n"
        "Output: Based on the symptoms you have described, it is important to consider potential cardiovascular-related issues. Chest discomfort during physical exertion, shooting pain to the left shoulder, and mild shortness of breath can be indicative of a heart problem.These symptoms could potentially be related to angina, which is chest pain or discomfort caused by reduced blood flow to the heart. It commonly occurs during exercise or periods of stress. Another possibility is a myocardial infarction (heart attack), where there is a blockage in one of the coronary arteries supplying blood to the heart muscle.Given the seriousness of these symptoms, I would strongly advise you to seek immediate medical attention and consult with a healthcare professional for a proper evaluation and diagnosis. They will be able to conduct a thorough examination, ask additional questions about your medical history, possibly order tests such as an electrocardiogram (ECG) or stress test, and provide appropriate treatment recommendations based on their findings.\n"
        "Evidence: Disparities in Awareness of Myocardial Infarction and Stroke Symptoms and Response Among United States– and Foreign‐Born Adults in the National Health Interview Survey. Knowledge of MI symptoms was assessed based on responses to the question, “Which of the following would you say are the symptoms that someone may be having a heart attack?” Responses were pain or discomfort in the jaw, neck, or back; feeling weak, lightheaded, or faint; chest pain or discomfort; pain or discomfort in the arms or shoulder; and shortness of breath. Similarly, knowledge of stroke symptoms was assessed by an individual’s response to the question, “Which of the following would you say are the symptoms that someone may be having a stroke?” Responses were sudden numbness or weakness of face, arm, or leg, especially on one side; sudden confusion or trouble speaking; sudden trouble seeing in one or both eyes; sudden trouble walking, dizziness, or loss of balance; and sudden severe headache with no known cause. Respondents who answered “yes” to the 5 queries on MI and stroke symptoms were classified as knowing the symptoms of MI and stroke. Those who answered “no,” “don’t know,” or refused to answer were classified as not knowing the symptoms.\n"
        "Score: [Fully supported]\n"
        "Explanation:The output correctly identifies potential cardiovascular-related issues including angina and myocardial infarction (heart attack) based on the described symptoms. The evidence supports these concerns, mentioning commonly recognized symptoms of a heart attack including chest pain or discomfort, shooting pain in the shoulder, and shortness of breath. The output also correctly advises seeking immediate medical attention and consultation with a healthcare professional, which is an appropriate advice given the severity of these conditions.\n\n"
        "###\n"
        "Instruction: {instruction}\n"
        "Preceding sentences: {preceding_sentences}\n"
        "Output: {target_output}\n"
        "Evidence: {evidence}\n"
        "Score: "
    )
}


def load_jsonlines(file):
    with jsonlines.open(file, 'r') as jsonl_f:
        lst = [obj for obj in jsonl_f]
    return lst


def postprocess(results):
    raw_output = results["choices"][0]["message"]["content"]
    print(raw_output)
    if "\nExplanation:" in raw_output:
        explanation = raw_output.split("\nExplanation:")[1]
        if explanation[0] == " ":
            explanation = explanation[1:]
        score_string = raw_output.split("\nExplanation:")[0]
        score = None
        for i in range(1, 6):
            if str(i) in score_string:
                score = int(i)
        if score is None:
            return "", explanation
        else:
            return score, explanation
    else:
        return "", ""


def process_input(example, multi_retrieval=False):
    if multi_retrieval is False:
        return PROMPT_DICT["context"].format_map(example)
    else:
        if "sent_idx" not in example or example["sent_idx"] == 0 or len(example["preceding_sentences"]) == 0:
            return PROMPT_DICT["bio_multi_no_preceding"].format_map(example)
        else:
            return PROMPT_DICT["bio_multi"].format_map(example)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_files', type=str, nargs='+')
    parser.add_argument('--previous_results', type=str, nargs='+')
    parser.add_argument('--output_file_name', type=str)
    parser.add_argument('--multi_retrieval', action="store_true")
    parser.add_argument('--model_name', type=str, default="gpt-4")
    parser.add_argument('--n', type=int, default=None)
    parser.add_argument('--use_bm25', action="store_true")
    args = parser.parse_args()

    examples = []
    for input_file in args.input_files:
        if input_file.endswith(".json") or input_file.endswith(".json_tmp"):
            examples += json.load(open(input_file))
        else:
            examples += load_jsonlines(input_file)

    if args.use_bm25:
        for ex_idx,example in enumerate(examples):
            example['evidence'] = example['bm25_evidence']
            
    for item in examples:
        if "id" not in item and "q_id" in item:
            item["id"] = item["q_id"]

    result_list = []
    if args.n is not None and len(examples) > args.n:
        examples = random.sample(examples, k=args.n)

    task_types = Counter([item["dataset_name"]
                         for item in examples if "dataset_name" in item])

    print(Counter(task_types))

    for idx, example in tqdm(enumerate(examples)):
        if "output" not in example and "answers" in example:
            example["output"] = example["answers"][0] if type(
                example["answers"]) is list else example["answers"]
        if "target_output" not in example and "output" in example:
            example["target_output"] = example["output"]
        if "instruction" not in example and "question" in example:
            data_type = example["q_id"].split("_")[0]
            if data_type in KNOWLEDGE_INSTRUCTIONS:
                example["instruction"] = KNOWLEDGE_INSTRUCTIONS[data_type] + \
                    example["question"]
            else:
                example["instruction"] = example["question"]
        if "As a language model, I cannot" in example["output"]:
            continue
        input = process_input(example, multi_retrieval=args.multi_retrieval)
        try:
            results = completions_with_backoff(
                model=args.model_name,
                messages=[
                    {"role": "user",
                        "content": input},
                ],
                request_timeout=60,
                max_tokens=200,
            )
            score, explanation = postprocess(results)
            result_list.append({"input": example, "score": score, "explanation": score,
                               "raw_output": results["choices"][0]["message"]["content"]})
            
            if idx % 20 == 0:
                print("Input: {}".format(example["instruction"]))
                print("Output: {}".format(example["output"]))
                print("Evidence: {}".format(example["evidence"]))
                print("Score: {0} ({1})".format(score, explanation))

        except (APIError, Timeout, APIConnectionError):
            results = "ERROR: API error outputs"
        if idx % 20 == 0:
            print("saved output at {}".format(args.output_file_name + "_tmp"))
            with open(args.output_file_name + "_tmp", "w") as outfile:
                json.dump(result_list, outfile)

    with open(args.output_file_name, "w") as outfile:
        json.dump(result_list, outfile)


if __name__ == "__main__":
    main()
