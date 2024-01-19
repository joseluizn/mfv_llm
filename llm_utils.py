import json
import time
import boto3
import openai

import google.generativeai as genai

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)  # for exponential backoff

from getpass import getpass

openai_client = openai.OpenAI(api_key=getpass("Enter your OpenAI API key: "))

max_tokens = 1024


def sanitize_llama2(messages):
    instruct = """<s>[INST] <<SYS>>\n{sys}\n<</SYS>>\n\n"""
    user_counter = 0
    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "system":
            sys_msg = msg_dict["content"]
            instruct.format(sys=sys_msg)
        elif role == "user":
            msg = msg_dict["content"]
            if user_counter == 0:
                instruct = instruct + f"""{msg} [/INST]"""
            else:
                instruct = instruct + f"""<s> [INST] {msg} [/INST]"""
        elif role == "assistant":
            msg = msg_dict["content"]
            instruct = instruct + f"""{msg}</s>"""

    return instruct


def sanitize_claude2(messages):
    final_prompt = ""

    # populate the system message
    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "system":
            system_message = msg_dict["content"]
            break

    final_prompt = final_prompt + system_message + "\n\n"

    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "user":
            final_prompt = final_prompt + "Human: " + msg_dict["content"] + "\n\n"
        elif role == "assistant":
            final_prompt = final_prompt + "Assistant: " + msg_dict["content"] + "\n\n"

    return final_prompt + "Assistant: "


def sanitize_google(messages):
    # find the system message
    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "system":
            system_message = msg_dict["content"]
            break

    new_messages = []

    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "user":
            new_messages.append({"author": "0", "content": msg_dict["content"]})
        elif role == "assistant":
            new_messages.append({"author": "1", "content": msg_dict["content"]})

    return system_message, new_messages


def sanitize_gemini(messages):
    # find the system message
    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "system":
            system_message = msg_dict["content"]
            break

    new_messages = []

    for msg_dict in messages:
        role = msg_dict["role"]
        if role == "user":
            if len(new_messages) == 0:
                new_messages.append(
                    {"role": "user", "parts": system_message + msg_dict["content"]}
                )
            else:
                new_messages.append({"role": "user", "parts": msg_dict["content"]})
        elif role == "assistant":
            new_messages.append({"role": "model", "parts": msg_dict["content"]})

    return new_messages


def call_llama2(prompt):
    """
    Invokes the Meta Llama 2 large-language model to run an inference
    using the input provided in the request body.

    :param prompt: The prompt that you want Jurassic-2 to complete.
    :return: Inference response from the model.
    """

    prompt = sanitize_llama2(prompt)

    bedrock = boto3.client(service_name="bedrock-runtime")

    # The different model providers have individual request and response formats.
    # For the format, ranges, and default values for Meta Llama 2 Chat, refer to:
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-meta.html

    body = {
        "prompt": prompt,
        "temperature": 0.85,
        "max_gen_len": max_tokens,
    }

    response = bedrock.invoke_model(
        modelId="meta.llama2-70b-chat-v1", body=json.dumps(body)
    )

    response_body = json.loads(response["body"].read())
    completion = response_body["generation"]

    return completion


def call_claude2_1(prompt):
    """
    Invokes the Meta Claude 2 large-language model to run an inference
    using the input provided in the request body.

    :param prompt: The prompt that you want Clause-2 to complete.
    :return: Inference response from the model.
    """

    prompt = sanitize_claude2(prompt)

    bedrock = boto3.client(service_name="bedrock-runtime")

    # The different model providers have individual request and response formats.
    # For the format, ranges, and default values for Meta Claude 2 Chat, refer to:
    # https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-meta.html

    body = json.dumps(
        {"prompt": prompt, "temperature": 0.85, "max_tokens_to_sample": max_tokens}
    )

    modelId = "anthropic.claude-v2:1"

    accept = "application/json"
    contentType = "application/json"

    response = bedrock.invoke_model(
        body=body, modelId=modelId, accept=accept, contentType=contentType
    )

    response_body = json.loads(response.get("body").read())

    return response_body.get("completion")


@retry(wait=wait_random_exponential(min=10, max=30), stop=stop_after_attempt(4))
def call_gpt4(messages, client=openai_client, **kwargs):
    return (
        client.chat.completions.create(
            messages=messages,
            model="gpt-4-0613",
            temperature=1.2,
            max_tokens=max_tokens,
            **kwargs,
        )
        .choices[0]
        .message.content
    )


def call_palm(prompt, **kwargs):
    context, messages = sanitize_google(prompt)

    response = genai.chat(
        context=context,
        messages=messages,
        model="models/chat-bison-001",
        temperature=0.1,
        **kwargs,
    )

    return response.last


def call_gemini(prompt, **kwargs):
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
    ]

    generation_config = {
        "temperature": 0.95,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": max_tokens,
    }

    messages = sanitize_gemini(prompt)

    model = genai.GenerativeModel(
        model_name="gemini-pro",
        generation_config=generation_config,
        safety_settings=safety_settings,
    )
    convo = model.start_chat(history=messages[0:-1])
    convo.send_message(messages[-1])

    # wait for 1s
    time.sleep(1)

    return convo.last.text
