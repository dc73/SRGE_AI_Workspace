-- Create the litellm database for LiteLLM proxy (virtual keys, spend tracking)
CREATE DATABASE litellm;
GRANT ALL PRIVILEGES ON DATABASE litellm TO coder;
