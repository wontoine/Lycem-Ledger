import SwiftUI
 
// --- Data Models (Unchanged) ---
struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct LoginResponse: Codable {
    let success: Bool
    let message: String
}


// --- View ---
// The View is now much simpler and is only responsible for layout and user actions.
struct ContentView: View {
    
    // Create and manage the lifecycle of the ViewModel.
    // Use camelCase for variable names.
    @StateObject private var viewModel = LoginViewModel()
    
    @State private var showingCreateAccountSheet = false
    @State private var showingForgotPasswordSheet = false

    
    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Spacer()
                
                Text("Lyceum Ledger")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .padding(.bottom, 30)
                
                Image("LyceumLedgerIcon")
                    .resizable()
                    .scaledToFit()
                
                // --- Input Fields ---
                // Bind directly to the ViewModel's properties.
                TextField("Username", text: $viewModel.username)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(10)
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                
                SecureField("Password", text: $viewModel.password)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(10)
                
                // --- Login Button ---
                Button(action: {
                    Task {
                        await viewModel.loginUser()
                    }
                }) {
                    Text("Log In")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .cornerRadius(10)
                }
                // --- UX Improvement ---
                // Disable the button based on the ViewModel's state.
                .disabled(viewModel.isLoginButtonDisabled)
                .opacity(viewModel.isLoginButtonDisabled ? 0.5 : 1.0)
                
                Button("create account"){
                    showingCreateAccountSheet = true
                }
                Button("Forgot Password") {
                                    showingForgotPasswordSheet = true
                                }
                
                // --- UI Feedback ---
                // This section reacts to changes in the ViewModel.
                if viewModel.isLoading {
                    ProgressView()
                }
                
                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                        .foregroundColor(.red)
                }
                
                // --- Programmatic Navigation ---
                // This invisible link activates when `isLoggedIn` becomes true.
               
                
                
                Spacer()
                Spacer()
            } // --- Modifier Placement ---
              // Modifiers are correctly attached to the VStack.
            .padding(.horizontal, 30)
            .navigationTitle("Log In")
            .navigationBarHidden(true)
            .navigationDestination(isPresented: $viewModel.isLoggedIn){
                Text("You are logged in!")
            }
            .sheet(isPresented: $showingCreateAccountSheet) {
                                    CreateAccountView()
                                }
            .sheet(isPresented: $showingForgotPasswordSheet) {
                            ForgotPasswordView()
                        }
        }
    }
}


struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
