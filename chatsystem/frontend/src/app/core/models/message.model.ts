export type SenderType = 'user' | 'bot' | 'human';
export type MessageStatus = 'pending' | 'processing' | 'processed' | 'error';

export interface Message {
  id: string;
  conversation_id: string;
  sender_type: SenderType;
  content: string;
  message_type: string;
  external_id: string | null;
  status: MessageStatus;
  created_at: string;
}
