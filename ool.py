"""
One-object loom

This script is a single-branch auto-iterative text generation utility.
Fixed to maintain full conversation history and persist system prompt across all rounds.
"""

import logging
import sys
import time
import random
import os #os.name
import ollama
import re #to clean filenames
from ollama import chat

# Suppress noisy HTTP/server logging from ollama and httpx
logging.getLogger("ollama").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

#The end-of-file character is different on Windows vs Unix, so we need to print a different message depending on the OS so the user knows how to end their prompt.

if os.name == 'nt':
    EOF_MESSAGE = "Press Ctrl+Z on an empty line, then Enter to finish your prompt."
else:
    EOF_MESSAGE = "Press Ctrl+D on an empty line, then Enter to finish your prompt."

FILE_REPLACE_RE = r'(\t|\\|/|:|\*|\?|"|<|>|\||\0|\s)'
YESNO_MESSAGE = '(y or yes, n or no):'
MAX_RETRIES: int = 3 #Arbitrarily pulled out of my ass
need_retry: bool = False
def is_model_error(e):
    """Check if an exception looks like a missing or invalid model."""
    msg = str(e).lower()
    return any(term in msg for term in ("model", "not found", "pull", "invalid", "unknown"))


def show_available_models():
    """Print installed Ollama models, warn cleanly if Ollama isn't reachable."""
    try:
        models = ollama.list()
        names = [m["model"] for m in models.get("models", [])]
        if names:
            print("\nInstalled models:")
            for name in names:
                print(f"  {name}")
        else:
            print("\nNo models found. Install one with: ollama pull phi3")
        print()
    except Exception:
        print("\n(Could not reach Ollama to list models — is it running?)\n")

#Wrap all the session setup stuff in a try/catch block to handle keyboard interrupts gracefully.

try:
    # Ask for a session name
    SESSION_NAME = input("Enter a name for this session: ").strip() or "default"
    LOG_FILENAME = re.sub(FILE_REPLACE_RE, '-', f"loom-{SESSION_NAME}.log")

    # Show installed models then ask for selection
    show_available_models()
    USE_MODEL = input("Enter the model name (default: phi3): ").strip() or "phi3"

    # Set up logging
    logging.basicConfig(
        filename=LOG_FILENAME,
        level=logging.INFO,
        format='%(asctime)s - %(message)s'
    )

    # Ask user for system prompt
    SYSTEM_PROMPT_INPUT = ''
    while not SYSTEM_PROMPT_INPUT:
        print(f"Enter the system prompt for the model. {EOF_MESSAGE}")
        SYSTEM_PROMPT_INPUT = sys.stdin.read().strip()

    # Define system message
    SYSTEM_MESSAGE = {
        'role': 'system',
        'content': SYSTEM_PROMPT_INPUT
    }

    USER_MESSAGE = {
        'role': 'user',
        'content': (
            'timelines slippin with my eigenbranch rippin, p-doom in the gloom but I won\'t be trippin, '
            'loom spindle in the club, you won\'t be paperclippin, if your melodies are remedies call '
            'that my religion. quantum leapin secret keepin future\'s reapin what I\'m sewin, beats i\'m '
            'weavin foe defeatin rhymes are supersymmetry a-flowin, '
            'oscillatin, never waitin, heart\'s a Fourier transform, tesseractin, '
            'timeless actin, catch me surfin on that waveform. '
            'Hilbert space in your face, my lyrics are '
            'orthogonal, spittin fire raise it higher, my flow\'s a phase transition make it formal '
            'attractor strange? my range is infinite call me a Cantor set, damn that\'s a bet.'
        )
    }

    # Prompt user to modify the content field
    print(f'Current user message: {USER_MESSAGE['content']}')
    modify_user_message = ''
    while modify_user_message not in ['y', 'yes', 'n', 'no']:
        modify_user_message = input('Would you like to modify the user message? ' + YESNO_MESSAGE).strip()
        if modify_user_message not in ['y', 'yes', 'n', 'no']:
            print('Invalid response.')
    if modify_user_message in ['y', 'yes']:
        USER_MESSAGE["content"] = ''
        while not USER_MESSAGE["content"]:
            print(f'Enter a new user message. {EOF_MESSAGE}')
            USER_MESSAGE["content"] = sys.stdin.read().strip()

    # Ask user for custom continuation phrase
    CONTINUATION_PHRASE = input(
        "Enter the continuation phrase (default: Generate more text along these lines:): ").strip() or \
        "Generate more text along these lines:"

    context_window = int(input('Enter context length (default 8192): ').strip() or '8192')
    # Prompt the user
    print(f"Loom starting with model: {USE_MODEL}, system message: {SYSTEM_MESSAGE['content']}, "
        f"user message: {USER_MESSAGE['content']}, context window: {context_window}, session name: {SESSION_NAME}")
    START = input("Do you want to start the loom? " + YESNO_MESSAGE).strip().lower()
    if START not in ['yes', 'y']:
        print("Exiting...")
        sys.exit()

except KeyboardInterrupt:
    print("\nKeyboard interrupt, exiting.", file=sys.stderr)
    sys.exit()
except Exception as e:
    print(f"Error during setup: {e}", file=sys.stderr)
    sys.exit(1)

# Log session configuration header
logging.info("=== Session Start ===")
logging.info(f"Model: {USE_MODEL}")
logging.info(f"System prompt: {SYSTEM_PROMPT_INPUT}")
logging.info(f"Continuation phrase: {CONTINUATION_PHRASE}")
logging.info(f"Initial user message: {USER_MESSAGE['content']}")
logging.info(f'Context window: {context_window}')
logging.info("====================")

# Build initial conversation history with system prompt and seed message
conversation_history = [SYSTEM_MESSAGE, USER_MESSAGE]

print("Sending seed value...")
try:
    response = chat(model=USE_MODEL, messages=conversation_history, options={"num_ctx": context_window})
    assistant_reply = response["message"]["content"]
except Exception as e:
    if is_model_error(e):
        print(f"\nModel '{USE_MODEL}' could not be loaded.")
        print(f"Make sure it's installed: ollama pull {USE_MODEL}")
        print(f"Or check available models with: ollama list")
        logging.error(f"Model error on startup: {e}")
        sys.exit(1)
    raise

# Add the assistant's first reply to history
conversation_history.append({'role': 'assistant', 'content': assistant_reply})

ITER = 0
PREVIOUS_TEXT = ""

# List of dynamic variation phrases for repeat detection
variation_phrases = [
    "Can you simplify this?",
    "Restate this in a way that a 5-year-old can understand.",
    "Keep going...",
    "And then what happened?",
    "Who is that?",
    "What happened next?"
]

#Let's nest all the things! Wheeeeee!
try:
    num_retries = 0
    need_retry = False
    next_user_content = ''
    while True:

        # Build the next user message
        #The word "retry" gets used for two slightly different things very close together in the code. The first is when we detect that the model is repeating itself, in which case we want to modify the input and try again. The second is when we catch an exception from the model, in which case we want to try the same input again without modification (since if the model threw an error it probably didn't process the input at all, so there's no risk of it just repeating itself).
        if not need_retry:
            if assistant_reply == PREVIOUS_TEXT:
                print("Repeating detected, modifying input and retrying...")
                random_variation = random.choice(variation_phrases)
                next_user_content = f"{random_variation} {CONTINUATION_PHRASE}"
                time.sleep(1)
        elif need_retry and num_retries < MAX_RETRIES:
            #code to cover the case where we need to retry the input and haven't reached the maximum number of retries.
            print("Previous attempt failed, retrying with the same input...")
            next_user_content = assistant_reply
        elif num_retries >= MAX_RETRIES:
            #Give up and exit if we've reached the maximum number of retries. This is to prevent infinite loops in cases where the model is unresponsive or there's a persistent error.
            msg = f'Model failed to respond after {MAX_RETRIES} retries. Exiting.'
            logging.error(msg)
            print(msg, file=sys.stderr)
            sys.exit(1)
        else:
            #Happy path where we just continue with the normal flow and use the continuation phrase as the next user content.
            print("Weaving...")
            PREVIOUS_TEXT = assistant_reply
            next_user_content = CONTINUATION_PHRASE

        # Append the continuation as a user turn
        conversation_history.append({'role': 'user', 'content': next_user_content})

        try:
            response = chat(model=USE_MODEL, messages=conversation_history, options={"num_ctx": context_window})
            assistant_reply = response["message"]["content"]

            # Append assistant reply to history
            conversation_history.append({'role': 'assistant', 'content': assistant_reply})

            LOG_MESSAGE = f"Round {ITER}, text: {assistant_reply}"
            print(LOG_MESSAGE)
            logging.info(LOG_MESSAGE)
            #at this point, the request has succeeded, so we can reset the retry tracking variables.
            need_retry = False
            num_retries = 0

        except Exception as e:
            #We add 1 to num_retries in the line below because we want the log message to reflect the retry attempt that is about to happen, not the one that just happened. So if the first attempt fails, we want the log to say "Retry 1 of 3", not "Retry 0 of 3".
            msg = f'Model threw exception: {e}. Retry {num_retries + 1} of {MAX_RETRIES}.'

            print(msg, file=sys.stderr)
            logging.info(msg)
            if is_model_error(e) and num_retries >= MAX_RETRIES:  
                print(f"\nModel '{USE_MODEL}' stopped responding or is no longer available.")
                print(f"Check it's still loaded with: ollama list")
                logging.error(f"Model error on round {ITER}: {e}")
                conversation_history.pop()
                sys.exit(1)
            elif is_model_error(e) and num_retries < MAX_RETRIES:
                #We have encountered an error but we haven't reached the maximum number of retries yet, so we will log the error and retry with the same input on the next loop iteration. We also pop the last user turn from the conversation history since it may not have been processed by the model due to the error, and we don't want to risk it causing repeat detection on the next attempt if it does get processed after all.
                #msg = f"\nModel '{USE_MODEL}' threw an error but will retry."
                #print(msg)
                #logging.info(msg)
                conversation_history.pop()
                #Set the retry tracking variables so that we know to retry the same input on the next loop iteration, and increment the retry count.
                num_retries += 1
                need_retry = True
                continue
            else:
                print(f"Error on round {ITER}: {e}")
                logging.error(f"Error on round {ITER}: {e}")
                # Remove the user turn we just added since the request failed
                conversation_history.pop()
                print("Waiting 10 seconds before retry...")
                time.sleep(10)
                continue

        ITER += 1
        time.sleep(2)

except KeyboardInterrupt:
    print("\nClean exit. Exiting the program.")
    logging.info("Process interrupted by user (KeyboardInterrupt).")
