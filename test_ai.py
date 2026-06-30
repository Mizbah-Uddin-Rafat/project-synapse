import os
from dotenv import load_dotenv
load_dotenv()

print('API KEY:', os.getenv('OPENAI_API_KEY')[:15] + '...' if os.getenv('OPENAI_API_KEY') else 'MISSING')
print('BASE URL:', os.getenv('OPENROUTER_BASE_URL'))
print('MODEL:', os.getenv('OPENAI_MODEL'))

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY'),
    base_url=os.getenv('OPENROUTER_BASE_URL'),
    default_headers={
        'HTTP-Referer': 'http://localhost:5000',
        'X-Title': 'Synapse'
    }
)

try:
    r = client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL'),
        messages=[{'role': 'user', 'content': 'hello'}],
        max_tokens=20
    )
    print('SUCCESS:', r.choices[0].message.content)
except Exception as e:
    print('FAILED:', repr(e))