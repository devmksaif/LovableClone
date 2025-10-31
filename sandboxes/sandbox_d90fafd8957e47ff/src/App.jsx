import React, { useState, useEffect } from 'react'
import { Plus, Search, Filter, Trash2, Edit2, Check, X, Calendar, Tag } from 'lucide-react'
import './App.css'

const TodoApp = () => {
  const [todos, setTodos] = useState(() => {
    const savedTodos = localStorage.getItem('todos')
    return savedTodos ? JSON.parse(savedTodos) : []
  })
  const [newTodo, setNewTodo] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [filter, setFilter] = useState('all')
  const [editingId, setEditingId] = useState(null)
  const [editText, setEditText] = useState('')
  const [category, setCategory] = useState('')

  useEffect(() => {
    localStorage.setItem('todos', JSON.stringify(todos))
  }, [todos])

  const addTodo = (e) => {
    e.preventDefault()
    if (newTodo.trim()) {
      const todo = {
        id: Date.now(),
        text: newTodo,
        completed: false,
        createdAt: new Date().toISOString(),
        category: category || 'general'
      }
      setTodos([...todos, todo])
      setNewTodo('')
      setCategory('')
    }
  }

  const toggleTodo = (id) => {
    setTodos(todos.map(todo => 
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    ))
  }

  const deleteTodo = (id) => {
    setTodos(todos.filter(todo => todo.id !== id))
  }

  const startEditing = (id, text) => {
    setEditingId(id)
    setEditText(text)
  }

  const saveEdit = () => {
    if (editText.trim()) {
      setTodos(todos.map(todo => 
        todo.id === editingId ? { ...todo, text: editText } : todo
      ))
    }
    setEditingId(null)
    setEditText('')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditText('')
  }

  const clearCompleted = () => {
    setTodos(todos.filter(todo => !todo.completed))
  }

  const filteredTodos = todos.filter(todo => {
    const matchesSearch = todo.text.toLowerCase().includes(searchTerm.toLowerCase())
    const matchesFilter = filter === 'all' || 
      (filter === 'active' && !todo.completed) || 
      (filter === 'completed' && todo.completed)
    return matchesSearch && matchesFilter
  })

  const categories = [...new Set(todos.map(todo => todo.category))]
  const activeTodos = todos.filter(todo => !todo.completed).length
  const completedTodos = todos.filter(todo => todo.completed).length

  return (
    <div className="todo-app">
      <div className="container">
        <header className="header">
          <h1>My Tasks</h1>
          <p className="subtitle">Stay organized and productive</p>
        </header>

        <div className="controls">
          <div className="search-bar">
            <Search size={20} />
            <input
              type="text"
              placeholder="Search tasks..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="filter-buttons">
            <button
              className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All
            </button>
            <button
              className={`filter-btn ${filter === 'active' ? 'active' : ''}`}
              onClick={() => setFilter('active')}
            >
              Active
            </button>
            <button
              className={`filter-btn ${filter === 'completed' ? 'active' : ''}`}
              onClick={() => setFilter('completed')}
            >
              Completed
            </button>
          </div>
        </div>

        <form onSubmit={addTodo} className="add-todo-form">
          <div className="input-group">
            <input
              type="text"
              placeholder="What needs to be done?"
              value={newTodo}
              onChange={(e) => setNewTodo(e.target.value)}
              className="todo-input"
            />
            <input
              type="text"
              placeholder="Category (optional)"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="category-input"
            />
            <button type="submit" className="add-btn">
              <Plus size={20} />
              Add Task
            </button>
          </div>
        </form>

        <div className="stats">
          <span>{activeTodos} active tasks</span>
          <span>{completedTodos} completed</span>
          {completedTodos > 0 && (
            <button onClick={clearCompleted} className="clear-btn">
              Clear completed
            </button>
          )}
        </div>

        <div className="todo-list">
          {filteredTodos.length === 0 ? (
            <div className="empty-state">
              <Calendar size={48} />
              <p>No tasks found</p>
              <span>Add a new task to get started!</span>
            </div>
          ) : (
            filteredTodos.map(todo => (
              <div key={todo.id} className={`todo-item ${todo.completed ? 'completed' : ''}`}>
                <div className="todo-content">
                  <button
                    className={`checkbox ${todo.completed ? 'checked' : ''}`}
                    onClick={() => toggleTodo(todo.id)}
                  >
                    {todo.completed && <Check size={16} />}
                  </button>
                  
                  {editingId === todo.id ? (
                    <div className="edit-form">
                      <input
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && saveEdit()}
                        autoFocus
                      />
                      <button onClick={saveEdit} className="save-btn">
                        <Check size={16} />
                      </button>
                      <button onClick={cancelEdit} className="cancel-btn">
                        <X size={16} />
                      </button>
                    </div>
                  ) : (
                    <div className="todo-text">
                      <span className="todo-text-content">{todo.text}</span>
                      {todo.category && (
                        <span className="category-tag">{todo.category}</span>
                      )}
                    </div>
                  )}
                </div>

                {editingId !== todo.id && (
                  <div className="todo-actions">
                    <button
                      onClick={() => startEditing(todo.id, todo.text)}
                      className="action-btn edit"
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => deleteTodo(todo.id)}
                      className="action-btn delete"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default TodoApp