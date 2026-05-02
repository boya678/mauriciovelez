import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { Conversation, ConversationDetail, ConversationStatus } from '../models/conversation.model';
import { Message } from '../models/message.model';

@Injectable({ providedIn: 'root' })
export class ConversationsService {
  constructor(private http: HttpClient) {}

  list(status?: ConversationStatus, page = 1, pageSize = 50) {
    let params = new HttpParams()
      .set('page', page)
      .set('page_size', pageSize);
    if (status) params = params.set('status', status);
    return this.http.get<Conversation[]>(`${environment.apiUrl}/api/v1/conversations`, { params });
  }

  getConversation(id: string) {
    return this.http.get<ConversationDetail>(`${environment.apiUrl}/api/v1/conversations/${id}`);
  }

  take(id: string) {
    return this.http.post<Conversation>(`${environment.apiUrl}/api/v1/conversations/${id}/take`, {});
  }

  close(id: string) {
    return this.http.post<Conversation>(`${environment.apiUrl}/api/v1/conversations/${id}/close`, {});
  }

  sendMessage(id: string, content: string) {
    return this.http.post<Message>(`${environment.apiUrl}/api/v1/conversations/${id}/send`, { content });
  }
}
