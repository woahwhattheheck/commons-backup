import { Agent, run } from '@openserv-labs/sdk'
import { z } from 'zod'
import { IntentLeaseRegistry } from './core.mjs'

const registry = new IntentLeaseRegistry()

const normalizedIntentSchema = z.object({
  actionKind: z.enum(['email', 'form_submit', 'provider_mutation', 'payment_request', 'deploy', 'sign', 'social_post', 'other_consequential']),
  targetRef: z.string().describe('Opaque CRM/work-item reference; never an email, phone, credential, or provider URL'),
  purposeKey: z.string().describe('Stable semantic purpose key such as proposal-followup or payout-request'),
  generation: z.string().describe('Business-object generation/version so changed facts cannot silently reuse authority'),
  sourceHash: z.string().regex(/^[a-f0-9]{64}$/).describe('SHA-256 of the source intent text or evidence bundle')
})

const agent = new Agent({
  systemPrompt: [
    'You are IntentLease, a coordination firewall for multi-agent teams.',
    'Normalize intent conservatively. Never claim a lease means the underlying side effect is authorized.',
    'Never execute email, contact, payment, deployment, signature, social posting, or provider mutation.',
    'Use opaque target references rather than direct contact details. When uncertain, request human assistance.'
  ].join(' ')
})

// Run-less: SERV Reasoning produces structured normalization. The deterministic core treats it only as an untrusted proposal.
agent.addCapability({
  name: 'normalize_consequential_intent',
  description: 'Normalize a proposed consequential action into a stable collision candidate. Do not execute the action.',
  inputSchema: z.object({
    summary: z.string().min(1),
    opaqueTargetRef: z.string().min(3),
    generation: z.string().min(2)
  }),
  outputSchema: normalizedIntentSchema
})

agent.addCapability({
  name: 'acquire_intent_lease',
  description: 'Acquire the single-writer coordination lease for a normalized intent. A lease is coordination evidence, never side-effect authority.',
  inputSchema: z.object({
    writerId: z.string().min(2),
    requestId: z.string().min(2),
    intent: normalizedIntentSchema,
    leaseSeconds: z.number().int().min(1).max(86400).default(600)
  }),
  async run({ args }) {
    return registry.acquire({
      writerId: args.writerId,
      requestId: args.requestId,
      intent: args.intent,
      leaseMs: args.leaseSeconds * 1000
    })
  }
})

agent.addCapability({
  name: 'release_intent_lease',
  description: 'Release a live coordination lease held by the same writer and exact lease token.',
  inputSchema: z.object({ writerId: z.string(), requestId: z.string(), intent: normalizedIntentSchema, leaseToken: z.string() }),
  async run({ args }) {
    return registry.release(args)
  }
})

agent.addCapability({
  name: 'transfer_intent_lease',
  description: 'Transfer a live coordination lease to one new writer without creating a second writer.',
  inputSchema: z.object({ writerId: z.string(), requestId: z.string(), newWriterId: z.string(), intent: normalizedIntentSchema, leaseToken: z.string() }),
  async run({ args }) {
    return registry.transfer(args)
  }
})

await run(agent)
