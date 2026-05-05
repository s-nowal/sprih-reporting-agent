import { BaseChatModel } from '@langchain/core/language_models/chat_models'
import { ChatGoogleGenerativeAI } from '@langchain/google-genai'
import { ChatGroq } from '@langchain/groq'
import { ChatOllama } from '@langchain/ollama'
import { AzureChatOpenAI, ChatOpenAI } from '@langchain/openai'
import { IndexedDBSaver } from '@/api/checkpoints'

import {
  AgentOptions,
  AzureOptions,
  GeminiOptions,
  GroqOptions,
  OllamaOptions,
  OpenAIOptions,
  ProviderOptions,
} from './types'

const ModelCreators: Record<string, (opts: any) => BaseChatModel> = {
  official: (opts: OpenAIOptions) => {
    return new ChatOpenAI({
      modelName: opts.model || 'gpt-5',
      configuration: {
        apiKey: opts.config.apiKey,
        baseURL: opts.config.baseURL || 'https://api.openai.com/v1',
      },
      temperature: opts.temperature ?? 0.7,
      maxTokens: opts.maxTokens ?? 800,
    })
  },

  ollama: (opts: OllamaOptions) => {
    return new ChatOllama({
      model: opts.ollamaModel,
      baseUrl: opts.ollamaEndpoint?.replace(/\/$/, '') || 'http://localhost:11434',
      temperature: opts.temperature,
    })
  },

  groq: (opts: GroqOptions) => {
    return new ChatGroq({
      model: opts.groqModel,
      apiKey: opts.groqAPIKey,
      temperature: opts.temperature ?? 0.5,
      maxTokens: opts.maxTokens ?? 1024,
    })
  },

  gemini: (opts: GeminiOptions) => {
    return new ChatGoogleGenerativeAI({
      model: opts.geminiModel ?? 'gemini-3-pro-preview',
      apiKey: opts.geminiAPIKey,
      temperature: opts.temperature ?? 0.7,
      maxOutputTokens: opts.maxTokens ?? 800,
    })
  },

  azure: (opts: AzureOptions) => {
    return new AzureChatOpenAI({
      model: opts.azureDeploymentName,
      temperature: opts.temperature ?? 0.7,
      maxTokens: opts.maxTokens ?? 800,
      azureOpenAIApiKey: opts.azureAPIKey,
      azureOpenAIEndpoint: opts.azureAPIEndpoint,
      azureOpenAIApiDeploymentName: opts.azureDeploymentName,
      azureOpenAIApiVersion: opts.azureAPIVersion ?? '2024-10-01',
    })
  },
}

const checkpointer = new IndexedDBSaver()

async function executeChatFlow(model: BaseChatModel, options: ProviderOptions): Promise<void> {
//   console.log("CHAT FLOW")
//   try {
//     if (!options.threadId) {
//       options.threadId = crypto.randomUUID()
//     }

//     const agent = createAgent({
//       model,
//       tools: [],
//       checkpointer,
//     })

//     const stream = await agent.stream(
//       { messages: options.messages },
//       {
//         signal: options.abortSignal,
//         configurable: { thread_id: options.threadId },
//         streamMode: 'messages',
//       },
//     )

//     let fullContent = ''

//     for await (const chunk of stream) {
//       if (options.abortSignal?.aborted) break

//       const content = typeof chunk[0].content === 'string' ? chunk[0].content : ''
//       fullContent += content
//       options.onStream(fullContent)
//     }

//   } catch (error: any) {
//     if (error.name === 'AbortError') throw error
//     options.errorIssue.value = true
//     console.error(error)
//   } finally {
//     options.loading.value = false
//   }
// }
    return;
}

type APImessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
}

function toAPIMessages(messages: any): APImessage[] {
  const msgs = Array.isArray(messages) ? messages : [messages]

  return msgs.map((msg: any) => {
    const type = msg._getType?.()

    return {
      role:
        type === 'human' ? 'user' :
        type === 'ai' ? 'assistant' :
        type === 'system' ? 'system' :
        'user',
      content:
        typeof msg.content === 'string'
          ? msg.content
          : JSON.stringify(msg.content),
    }
  })
}

import { BASE_URL } from './config'

async function ensureThread(threadId: string): Promise<string> {
  const res = await fetch(`${BASE_URL}/threads/${threadId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })

  if (res.ok) {
    return threadId
  }

  const createRes = await fetch(`${BASE_URL}/threads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId })
  })

  const data = await createRes.json()
  return data.thread_id
}

export async function executeAgentFlow(options: AgentOptions): Promise<void> {
  options.threadId = await ensureThread(options.threadId!)

  try {
    await runStreaming(options)
  } catch (streamError: any) {
    console.warn('[Agent] Streaming failed, falling back to sync:', streamError)
    await runSync(options)
  }
}

async function runStreaming(options: AgentOptions): Promise<void> {
  const resumeVal = options.resumeValue
  options.resumeValue = undefined

  const body = resumeVal !== undefined
    ? {
        assistant_id: 'reporting-agent',
        command: { resume: resumeVal },
        stream_mode: 'values'
      }
    : (() => {
      const msgs = Array.isArray(options.messages)
        ? options.messages
        : [options.messages]

      const isFirstMessage = msgs.length === 1
      const lastMessage = msgs[msgs.length - 1]

      const messagesToSend = isFirstMessage
        ? msgs
        : [lastMessage]

      return {
        assistant_id: 'reporting-agent',
        input: { messages: toAPIMessages(messagesToSend) },
        stream_mode: 'values'
      }
    })()

  const response = await fetch(
    `${BASE_URL}/threads/${options.threadId}/runs/stream`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options.abortSignal,
    }
  )

  if (!response.ok) throw new Error(`Stream failed: ${response.status}`)

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let fullContent = ''
  let stepCount = 0
  let interrupted = false
  let interruptTriggered = false
  const processedToolCallIds = new Set<string>()
  let currentEvent = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const raw = line.slice(6).trim()
        if (!raw || raw === 'null') continue

        try {
          const payload = JSON.parse(raw)

          if (currentEvent === 'interrupt') {
            const interrupt = Array.isArray(payload) ? payload[0] : payload
            interrupted = true

            if (options.onInterrupt) {
              options.onInterrupt(
                interrupt.value?.message ?? interrupt.value
              )
            }
            continue
          }
          if (interrupted) continue

          if (currentEvent === 'values' && payload.messages) {
            stepCount++
            const lastMessage = payload.messages[payload.messages.length - 1] as any
            if (!lastMessage) continue
            
            if (lastMessage.type === 'ai') {
              if (Array.isArray(lastMessage.content)) {
                const toolUseBlocks = lastMessage.content.filter(
                  (block: any) => block.type === 'tool_use'
                )

                if (toolUseBlocks.length > 0 && options.onToolCall) {
                  for (const block of toolUseBlocks) {
                    if (processedToolCallIds.has(block.id)) continue
                    processedToolCallIds.add(block.id)
                    if (block.name === 'request_user_input') interruptTriggered = true
                    options.onToolCall(block.name, block.input, block.id)  // await here
                  }
                }

                const textBlocks = lastMessage.content.filter(
                  (block: any) => block.type === 'text'
                )
                if (textBlocks.length > 0 && !interruptTriggered) {
                  fullContent = textBlocks.map((b: any) => b.text).join('')
                  options.onStream(fullContent)
                }
              }

              if (typeof lastMessage.content === 'string' && lastMessage.content) {
                interruptTriggered = false
                fullContent += (fullContent ? '\n' : '') + lastMessage.content
                options.onStream(fullContent)
              }
            }

            if (lastMessage.type === 'tool' && options.onToolResult) {
              options.onToolResult(
                lastMessage.name || 'tool',
                String(lastMessage.content || '')
              )
            }
          }

          if (currentEvent === 'error') {
            console.error('[Agent] Error event:', payload)
            options.errorIssue.value = true
          }
        } catch {}
      }
    }
  }
}

async function runSync(options: AgentOptions): Promise<void> {
  const body = options.resumeValue !== undefined
    ? {
        assistant_id: 'reporting-agent',
        command: { resume: options.resumeValue },
      }
    : (() => {
      const msgs = Array.isArray(options.messages)
        ? options.messages
        : [options.messages]

      const isFirstMessage = msgs.length === 1
      const lastMessage = msgs[msgs.length - 1]

      const messagesToSend = isFirstMessage
        ? msgs
        : [lastMessage]

      return {
        assistant_id: 'reporting-agent',
        input: { messages: toAPIMessages(messagesToSend) },
      }
    })()

  const response = await fetch(
    `${BASE_URL}/threads/${options.threadId}/runs/wait`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: options.abortSignal,
    }
  )

  if (!response.ok) throw new Error(`Sync run failed: ${response.status}`)

  const data = await response.json()
  const messages = data.messages ?? []
  const lastAI = [...messages].reverse().find((m: any) => m.type === 'ai' && m.content && !m.tool_calls?.length)

  if (lastAI) {
    const content = typeof lastAI.content === 'string' ? lastAI.content : ''
    options.onStream(content)
  }
}

export async function getChatResponse(options: ProviderOptions) {
  const creator = ModelCreators[options.provider]
  if (!creator) throw new Error(`Unsupported provider: ${options.provider}`)
  const model = creator(options)
  return executeChatFlow(model, options)
}

export async function getAgentResponse(options: AgentOptions) {
  const creator = ModelCreators[options.provider]
  if (!creator) throw new Error(`Unsupported provider: ${options.provider}`)
  return executeAgentFlow(options)
}