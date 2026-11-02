export type CatalogAction = 'status' | 'sources' | 'source:save' | 'messages' | 'message' | 'templates' | 'template:save' | 'template:publish' | 'template:archive' | 'preview' | 'fields' | 'links' | 'links:save' | 'reviews' | 'review:ignore' | 'search' | 'process' | 'reprocess:preview' | 'reprocess:confirm' | 'reprocess:cancel'
export type CatalogRequest = { action: CatalogAction | 'alerts' | 'alerts:save' | 'deliveries' | 'review:examples' | 'review:split' | 'reprocess:list' | 'reprocess:resume' | 'source:history' | 'run'; [key: string]: unknown }
export interface Source { id: number; name: string; enabled: number; capture_started_at: string; checkpoint: string | null; revision: number; degraded: string | null }
export interface CatalogStatus { messages: number; revisions: number; pending: number; runs: number; offers: number; reviews: number; bytes: number; sources: Source[] }
export interface Page<T> { items: T[]; total: number; offset?: number; limit?: number }
export interface ArchivedMessage { id: number; source_id: number; message_id: number; published_at: string; revision_at: string; text: string; source_name: string; state: string | null }
export interface MessageDetail extends ArchivedMessage { metadata: { links: { url: string; origin: string; start?: number }[]; media_type: string | null }; revisions: { id: number; revision_at: string }[]; runs: { id: number; state: string; created_at: string; result: string }[]; run_history: { id: number; state: string; created_at: string }[] }
export type FieldType = 'text' | 'money' | 'number' | 'condition' | 'category' | 'link' | 'installments'
export interface FieldDefinition { id: string; name: string; type: FieldType }
export interface FieldMapping { field_id: string; name: string; type: FieldType; op: 'after' | 'between' | 'line' | 'presence' | 'constant' | 'link'; marker?: string; end?: string; line?: number; value?: string; scope?: 'offer' | 'message' | 'price'; option?: string; required?: boolean; many?: boolean; mapping?: Record<string, string>; absence?: 'unknown' | 'absent'; position?: number; host?: string }
export interface Template { id: string; name: string; source_id: number; markers: string[]; delimiter: string; block_marker?: string; kind?: 'offer' | 'ignore'; fields: FieldMapping[] }
export interface TemplateEntry { id: string; source_id: number; revision: number; draft: Template; published: number | null; archived: number }
export interface LinkRule { host: string; store: string; subdomains: boolean }
export interface LinkSettings { rules: LinkRule[]; revision: number }
export interface OfferValue { name: string; type: FieldType; value: unknown; raw: string; start: number | null; origin: string; scope: string; option: string | null; evidence: { raw: string; start: number | null; origin: string }[] }
export interface ExtractedOffer { block: number; values: Record<string, OfferValue> }
export interface Extraction { state: string; field_id?: string; offers: ExtractedOffer[]; template_id?: string; version?: number }
export interface OfferRecord { id: number; source_id: number; revision_id: number; published_at: string; source_name: string; payload: ExtractedOffer }
export interface Review { source_id: number; source_name: string; reason: string; signature: string; count: number; example_id: number; first_at: string; last_at: string }
export interface ReprocessPreview { token: string; count: number }
export interface WorkerStatus { running: boolean; error: string | null }
export interface ValueFilter { field_id: string; min?: number; max?: number; text?: string; option?: string; presence?: string }
export interface StructuredRule { id: string; name: string; source_id: number; enabled: boolean; filters: { values: ValueFilter[] }; activated_at?: string }
export interface StructuredSettings { rules: StructuredRule[]; revision: number }
export interface Delivery { id: number; rule_name: string; source_id: number; message_id: number; state: string; error: string | null; created_at: string }
export interface ReprocessJob { token: string; created_at: string; state: string; total: number; pending: number; done: number; cancelled: number }
