"""Ask one question through the OpenAI API and print the answer."""
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "In one short sentence, what is a lighthouse for?"},
    ],
)
answer = response.choices[0].message.content
if not answer or not answer.strip():
    raise SystemExit("empty completion")
print(answer)
