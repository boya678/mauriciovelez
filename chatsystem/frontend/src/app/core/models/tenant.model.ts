export interface TenantOut {
  id: string;
  name: string;
  slug: string;
  active: boolean;
  created_at: string;
  whatsapp_phone_id: string | null;
  whatsapp_token: string | null;
  webhook_secret: string | null;
  ai_system_prompt: string | null;
  whatsapp_template_name: string | null;
  whatsapp_template_language: string | null;
}

export interface TenantCreate {
  name: string;
  slug: string;
  whatsapp_phone_id: string | null;
  whatsapp_token: string | null;
  webhook_secret: string | null;
  ai_system_prompt: string | null;
  whatsapp_template_name: string | null;
  whatsapp_template_language: string | null;
}

export interface TenantUpdate {
  name?: string;
  whatsapp_phone_id?: string | null;
  whatsapp_token?: string | null;
  webhook_secret?: string | null;
  ai_system_prompt?: string | null;
  whatsapp_template_name?: string | null;
  whatsapp_template_language?: string | null;
}
