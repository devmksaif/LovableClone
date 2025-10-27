import { useState, useEffect } from 'react';

interface Session {
  id: string;
  sessionId: string;
  projectFolder: string;
  createdAt: string;
  updatedAt: string;
  conversations: Array<{
    id: string;
    role: string;
    content: string;
    timestamp: string;
  }>;
  projects: Array<{
    id: string;
    projectFolder: string;
    userRequest: string;
    plan: string[];
    isComplete: boolean;
    createdAt: string;
    files: Array<{
      filename: string;
      operation: string;
    }>;
  }>;
}

interface ChatSidebarProps {
  currentSessionId: string;
  onSessionSelect: (sessionId: string) => void;
  onNewProject: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface PaginationInfo {
  page: number;
  pageSize: number;
  totalSessions: number;
  totalPages: number;
  hasNextPage: boolean;
  hasPrevPage: boolean;
}

export function ChatSidebar({ currentSessionId, onSessionSelect, onNewProject, isCollapsed = false, onToggleCollapse }: ChatSidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState<PaginationInfo | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 5;

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async (page: number = 1) => {
    try {
      setLoading(true);
      const response = await fetch(`/api/sessions?page=${page}&pageSize=${pageSize}`);
      if (!response.ok) {
        throw new Error('Failed to load sessions');
      }
      const data = await response.json();
      setSessions(data.sessions || []);
      setPagination(data.pagination);
      setCurrentPage(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);

    if (diffHours < 24) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffHours < 168) { // 7 days
      return date.toLocaleDateString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  const getProjectTitle = (session: Session) => {
    if (session.projects.length > 0) {
      const latestProject = session.projects[0];
      // Extract a short title from the user request
      const request = latestProject.userRequest;
      return request.length > 40 ? request.substring(0, 40) + '...' : request;
    }
    return 'New Project';
  };

  const getLastMessage = (session: Session) => {
    if (session.conversations.length > 0) {
      const lastConv = session.conversations[session.conversations.length - 1];
      const content = lastConv.content;
      return content.length > 50 ? content.substring(0, 50) + '...' : content;
    }
    return 'No messages yet';
  };

  return (
    <>
      {/* Backdrop */}
      {!isCollapsed && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40"
          onClick={onToggleCollapse}
        />
      )}

      {/* Sidebar */}
      <div className={`fixed left-0 top-0 h-full z-50 transition-all duration-300 ease-in-out ${
        isCollapsed ? 'w-12' : 'w-80'
      } bg-white border-r border-gray-200 flex flex-col shadow-lg`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-4">
          {!isCollapsed && <h2 className="text-lg font-semibold text-gray-800">Projects</h2>}
          <button
            onClick={onToggleCollapse}
            className="p-1 hover:bg-gray-100 rounded transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? '→' : '←'}
          </button>
        </div>
        {!isCollapsed && (
          <div className="text-xs text-gray-500">
            {pagination ? `${pagination.totalSessions} project${pagination.totalSessions !== 1 ? 's' : ''}` : `${sessions.length} project${sessions.length !== 1 ? 's' : ''}`}
          </div>
        )}
      </div>

      {/* Sessions List */}
      {!isCollapsed && (
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-center text-gray-500">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mx-auto mb-2"></div>
              Loading projects...
            </div>
          ) : error ? (
            <div className="p-4 text-center text-red-500">
              <div className="text-sm">{error}</div>
              <button
                onClick={() => loadSessions()}
                className="mt-2 text-xs text-blue-500 hover:text-blue-600"
              >
                Try again
              </button>
            </div>
          ) : sessions.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              <div className="text-2xl mb-2">📁</div>
              <div className="text-sm">No projects yet</div>
              <button
                onClick={onNewProject}
                className="mt-2 text-xs text-blue-500 hover:text-blue-600"
              >
                Create your first project
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {sessions.map((session) => (
                <div
                  key={session.sessionId}
                  onClick={() => onSessionSelect(session.sessionId)}
                  className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                    session.sessionId === currentSessionId ? 'bg-blue-50 border-r-2 border-blue-500' : ''
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-medium text-gray-900 truncate">
                        {getProjectTitle(session)}
                      </h3>
                      <p className="text-xs text-gray-500 mt-1">
                        {formatDate(session.updatedAt)}
                      </p>
                    </div>
                    {session.projects.some(p => p.isComplete) && (
                      <div className="ml-2 flex-shrink-0">
                        <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                      </div>
                    )}
                  </div>

                  <p className="text-xs text-gray-600 line-clamp-2">
                    {getLastMessage(session)}
                  </p>

                  <div className="flex items-center justify-between mt-2 text-xs text-gray-400">
                    <span>{session.conversations.length} messages</span>
                    <span>{session.projects.length} builds</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Collapsed State - Show New Button */}
      {isCollapsed && (
        <div className="flex-1 flex flex-col items-center justify-center p-2">
          <button
            onClick={onNewProject}
            className="w-8 h-8 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors flex items-center justify-center text-lg"
            title="New Project"
          >
            +
          </button>
        </div>
      )}

      {/* Footer */}
      {!isCollapsed && (
        <div className="p-4 border-t border-gray-200">
          {/* Pagination Controls */}
          {pagination && pagination.totalPages > 1 && (
            <div className="mb-3">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-2">
                <span>Page {pagination.page} of {pagination.totalPages}</span>
                <span>{pagination.totalSessions} total</span>
              </div>
              <div className="flex items-center justify-between">
                <button
                  onClick={() => loadSessions(currentPage - 1)}
                  disabled={!pagination.hasPrevPage || loading}
                  className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ← Prev
                </button>
                <div className="flex space-x-1">
                  {Array.from({ length: Math.min(5, pagination.totalPages) }, (_, i) => {
                    const pageNum = i + 1;
                    return (
                      <button
                        key={pageNum}
                        onClick={() => loadSessions(pageNum)}
                        disabled={loading}
                        className={`px-2 py-1 text-xs rounded ${
                          pageNum === currentPage
                            ? 'bg-blue-500 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={() => loadSessions(currentPage + 1)}
                  disabled={!pagination.hasNextPage || loading}
                  className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next →
                </button>
              </div>
            </div>
          )}

          <div className="text-xs text-gray-500 text-center">
            Projects are automatically saved
          </div>
        </div>
      )}
      </div>
    </>
  );
}