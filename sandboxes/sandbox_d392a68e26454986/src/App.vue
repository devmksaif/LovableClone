<template>
  <div class="font-sans antialiased text-center text-gray-800 max-w-2xl mx-auto p-6 rounded-xl shadow-lg border border-gray-200 bg-white">
    <h1 class="text-3xl font-bold text-gray-800 mb-8">Todo App</h1>

    <div class="flex mb-6">
      <input
        v-model="newTodoText"
        @keyup.enter="addTodo"
        placeholder="Add a new todo"
        class="flex-grow p-3 border border-gray-300 rounded-l-md mr-2 focus:outline-none focus:ring-2 focus:ring-green-500"
      />
      <button
        @click="addTodo"
        class="px-5 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-colors duration-200"
      >
        Add Todo
      </button>
    </div>

    <div class="flex justify-center gap-3 mb-6">
      <button
        @click="filter = 'all'"
        :class="{ 'bg-green-500 text-white': filter === 'all', 'bg-gray-100': filter !== 'all' }"
        class="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-200 active:bg-gray-300 transition-colors duration-200"
      >All</button>
      <button
        @click="filter = 'active'"
        :class="{ 'bg-green-500 text-white': filter === 'active', 'bg-gray-100': filter !== 'active' }"
        class="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-200 active:bg-gray-300 transition-colors duration-200"
      >Active</button>
      <button
        @click="filter = 'completed'"
        :class="{ 'bg-green-500 text-white': filter === 'completed', 'bg-gray-100': filter !== 'completed' }"
        class="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-200 active:bg-gray-300 transition-colors duration-200"
      >Completed</button>
    </div>

    <transition-group name="list" tag="ul" class="space-y-3" appear>
      <li
        v-for="todo in filteredTodos"
        :key="todo.id"
        :class="{ 'line-through text-gray-400': todo.done }"
        class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100"
      >
        <div class="flex items-center">
          <input
            type="checkbox"
            v-model="todo.done"
            class="w-5 h-5 text-green-500 rounded focus:ring-green-500"
          />
          <span class="ml-3 text-left flex-grow">{{ todo.text }}</span>
        </div>
        <button
          @click="removeTodo(todo.id)"
          class="px-3 py-1 text-sm bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors"
        >
          Delete
        </button>
      </li>
    </ul>
  </div>
</template>

<script>
let id = 0;

export default {
  name: 'App',
  data() {
    return {
      newTodoText: '',
      todos: [
        { id: id++, text: 'Learn Vue', done: false },
        { id: id++, text: 'Build a Todo App', done: true },
        { id: id++, text: 'Deploy to production', done: false }
      ],
      filter: 'all'
    };
  },
  computed: {
    filteredTodos() {
      if (this.filter === 'active') {
        return this.todos.filter(todo => !todo.done);
      } else if (this.filter === 'completed') {
        return this.todos.filter(todo => todo.done);
      }
      return this.todos;
    }
  },
  methods: {
    addTodo() {
      if (this.newTodoText.trim()) {
        this.todos.push({ id: id++, text: this.newTodoText, done: false });
        this.newTodoText = '';
      }
    },
    removeTodo(id) {
      this.todos = this.todos.filter(todo => todo.id !== id);
    }
  }
};
</script>

<style scoped>
/* Tailwind styles will be applied via utility classes in the template */

/* Transition animations for todo items */
.list-enter-active, .list-leave-active {
  transition: all 0.3s ease;
}
.list-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}
.list-enter-to {
  opacity: 1;
  transform: translateY(0);
}
.list-leave-from {
  opacity: 1;
  transform: translateY(0);
}
.list-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
.list-move {
  transition: transform 0.3s;
}
</style>
