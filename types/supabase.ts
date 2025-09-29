export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "13.0.5"
  }
  public: {
    Tables: {
      analytics_dashboards: {
        Row: {
          created_at: string | null
          dashboard_name: string
          id: string
          is_default: boolean | null
          updated_at: string | null
          user_anonymous_id: string
          widget_config: Json
        }
        Insert: {
          created_at?: string | null
          dashboard_name: string
          id?: string
          is_default?: boolean | null
          updated_at?: string | null
          user_anonymous_id: string
          widget_config: Json
        }
        Update: {
          created_at?: string | null
          dashboard_name?: string
          id?: string
          is_default?: boolean | null
          updated_at?: string | null
          user_anonymous_id?: string
          widget_config?: Json
        }
        Relationships: []
      }
      analytics_events: {
        Row: {
          anonymous_id: string
          created_at: string | null
          event_data: Json | null
          event_type: string
          id: string
          session_id: string | null
        }
        Insert: {
          anonymous_id: string
          created_at?: string | null
          event_data?: Json | null
          event_type: string
          id?: string
          session_id?: string | null
        }
        Update: {
          anonymous_id?: string
          created_at?: string | null
          event_data?: Json | null
          event_type?: string
          id?: string
          session_id?: string | null
        }
        Relationships: []
      }
      users: {
        Row: {
          anonymous_id: string
          created_at: string | null
          first_name: string | null
          id: string
          last_active: string | null
          permissions: Json | null
          preferences: Json | null
          role: string | null
          telegram_id: number
          updated_at: string | null
          username: string | null
        }
        Insert: {
          anonymous_id: string
          created_at?: string | null
          first_name?: string | null
          id?: string
          last_active?: string | null
          permissions?: Json | null
          preferences?: Json | null
          role?: string | null
          telegram_id: number
          updated_at?: string | null
          username?: string | null
        }
        Update: {
          anonymous_id?: string
          created_at?: string | null
          first_name?: string | null
          id?: string
          last_active?: string | null
          permissions?: Json | null
          preferences?: Json | null
          role?: string | null
          telegram_id?: number
          updated_at?: string | null
          username?: string | null
        }
        Relationships: []
      }
      courses: {
        Row: {
          anonymous_contributor: string
          approval_date: string | null
          category: string
          created_at: string | null
          description: string | null
          file_attachments: Json | null
          id: string
          metadata: Json | null
          published_at: string | null
          status: string | null
          tags: Json | null
          title: string
          updated_at: string | null
        }
        Insert: {
          anonymous_contributor: string
          approval_date?: string | null
          category: string
          created_at?: string | null
          description?: string | null
          file_attachments?: Json | null
          id?: string
          metadata?: Json | null
          published_at?: string | null
          status?: string | null
          tags?: Json | null
          title: string
          updated_at?: string | null
        }
        Update: {
          anonymous_contributor?: string
          approval_date?: string | null
          category?: string
          created_at?: string | null
          description?: string | null
          file_attachments?: Json | null
          id?: string
          metadata?: Json | null
          published_at?: string | null
          status?: string | null
          tags?: Json | null
          title?: string
          updated_at?: string | null
        }
        Relationships: []
      }
      // ... Additional table types would continue here
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
